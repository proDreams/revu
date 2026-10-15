"""One review, start to finish, whoever asked for it.

The webhook server and the CI command want the same thing: look at a change, say
something useful about it, and put the answer where the author will see it. They
differ only in where the change comes from and where the answer goes — a host API
against a local checkout, a pull request comment against a job log.

So the scenario lives here and takes its source and its destination as arguments.
Everything that made the review good stays in one place: the previous conversation
is read and built upon, the diff is annotated with line numbers so inline comments
can be anchored, unanchorable ones are dropped, every comment is signed, and the
cost is logged in one line.
"""

from dataclasses import dataclass, replace

from unidiff import PatchSet

from revu.application.config import get_logger
from revu.application.entities import review_marker
from revu.application.entities.config import GitConnectionConfig
from revu.application.entities.enums.review_mode_enums import ReviewModeEnum
from revu.application.entities.exceptions.review_service_exceptions import (
    ReviewModeException,
)
from revu.application.services.context_builder import ContextBuilder, ContextRequest
from revu.application.services.diff_anchors import DiffAnchors, drop_unanchored_comments
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.dto.code_context_dto import CHARS_PER_TOKEN, CodeContextDTO
from revu.domain.entities.dto.review_context_dto import ReviewContextDTO
from revu.domain.entities.dto.review_task_dto import ReviewTask
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.domain.protocols.comment_publisher_protocol import CommentPublisherProtocol
from revu.domain.protocols.git_reader_protocol import GitReaderProtocol

logger = get_logger(name=__name__)


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    """What is being reviewed, and where its outcome belongs."""

    #: Repository the change lives in, ``owner/name`` as the host spells it.
    repo: str
    #: Pull request (or merge request) number.
    number: int
    title: str
    body: str | None
    #: The commit the review is about; inline comments are anchored to it.
    revision: str


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    """What a review produced, for the caller to gate on."""

    mode: ReviewModeEnum
    #: How many comments reached the publisher.
    published: int
    #: Inline findings, which is what a quality gate can count. Comment mode says
    #: its piece in prose and reports none: there is nothing structured to gate on.
    findings: int
    #: Inline comments thrown away because their lines are not in the diff.
    dropped: int
    #: Whether this was a follow-up to an earlier review.
    re_review: bool
    code_context: CodeContextDTO


class ReviewRunner:
    """Runs one review. Stateless: everything it needs arrives as an argument."""

    def __init__(self, context_builder: ContextBuilder) -> None:
        self._context_builder = context_builder

    async def run(
        self,
        *,
        reader: GitReaderProtocol,
        publisher: CommentPublisherProtocol,
        ai_port: AIProviderProtocol,
        config: GitConnectionConfig,
        request: ReviewRequest,
    ) -> ReviewOutcome:
        """Review one change and publish the result."""
        diff = await reader.fetch_diff(repo=request.repo, index=request.number)

        context = await self._fetch_review_context(reader, config, request)
        code_context = await self._fetch_code_context(reader, config, request, diff)

        task = ReviewTask(
            diff=diff,
            git_host=config.host,
            pr_title=request.title,
            pr_body=request.body,
            system_prompt=config.system_prompt,
            previous_review=context,
            code_context=code_context,
        )

        # A model reading a diff this size is not fast, and the wait is the longest
        # silence in the log: say what is being waited for, and on how much.
        logger.info(
            "asking the model about %s#%s on connection %s (mode %s): diff=%d chars, context=%d entries",
            request.repo,
            request.number,
            config.key,
            # Not `.value`: an unknown mode reaches this line before the branch that
            # rejects it, and the log must not be the thing that fails first.
            config.review_mode,
            len(task.diff),
            len(code_context.entries),
        )

        outcome = await self._publish(
            publisher=publisher,
            ai_port=ai_port,
            config=config,
            request=request,
            task=task,
            context=context,
            code_context=code_context,
        )

        return outcome

    async def _publish(
        self,
        *,
        publisher: CommentPublisherProtocol,
        ai_port: AIProviderProtocol,
        config: GitConnectionConfig,
        request: ReviewRequest,
        task: ReviewTask,
        context: ReviewContextDTO | None,
        code_context: CodeContextDTO,
    ) -> ReviewOutcome:
        re_review = self._is_re_review(context)

        match config.review_mode:
            case ReviewModeEnum.COMMENT:
                str_review = await ai_port.get_comment_response(task)

                await publisher.send_comment(
                    repo_owner=request.repo,
                    review=self._sign_summary(str_review, context),
                    index=request.number,
                )

                return ReviewOutcome(
                    mode=config.review_mode,
                    published=1,
                    findings=0,
                    dropped=0,
                    re_review=re_review,
                    code_context=code_context,
                )
            case ReviewModeEnum.INLINE:
                annotated_diff = self.annotate_diff(diff_text=task.diff)

                dto_review = await ai_port.get_inline_response(replace(task, diff=annotated_diff))

                dto_review = self._sign_inline_review(dto_review, context)

                dto_review, dropped = drop_unanchored_comments(
                    dto_review,
                    DiffAnchors.from_diff(task.diff),
                    config.host,
                )

                if dropped:
                    logger.warning(
                        "dropped %d of %d inline comments for connection %s: their lines are not in the diff",
                        dropped,
                        dropped + len(dto_review.comments),
                        config.key,
                    )

                await publisher.send_inline(
                    sha=request.revision,
                    repo_owner=request.repo,
                    review=dto_review,
                    index=request.number,
                )

                return ReviewOutcome(
                    mode=config.review_mode,
                    published=len(dto_review.comments),
                    findings=len(dto_review.comments),
                    dropped=dropped,
                    re_review=re_review,
                    code_context=code_context,
                )
            case _:
                raise ReviewModeException("Unknown review mode")

    async def _fetch_review_context(
        self,
        reader: GitReaderProtocol,
        config: GitConnectionConfig,
        request: ReviewRequest,
    ) -> ReviewContextDTO | None:
        """What the pull request already says, or ``None`` for a first review.

        Reading the history is how a second review avoids repeating itself, but it
        is not worth losing a review over: a host that refuses the call (an older
        token without the right scope, a blocked endpoint) costs only the context,
        and the review continues from the diff alone.
        """
        try:
            context = await reader.fetch_review_context(repo=request.repo, index=request.number)
        except Exception:
            logger.warning(
                "could not read the earlier comments for connection %s, %s#%s; reviewing without them",
                config.key,
                request.repo,
                request.number,
            )
            return None

        if context is None or config.include_pr_discussion:
            return context

        # ReVu's own findings are its own output; only other people's words are
        # held back when a connection asks for that.
        return ReviewContextDTO(comments=context.findings)

    @staticmethod
    def _progress_line(review: ReviewResponseDTO, context: ReviewContextDTO | None) -> str | None:
        """How many earlier findings were addressed, when that can be said.

        The total is ReVu's own count, so a model reporting fewer findings cannot
        shrink it; a model reporting none at all gets no line rather than a claim of
        zero fixes.
        """
        if context is None or not context.findings:
            return None

        total = len(context.findings)
        reported = review.previous_findings or []

        if not reported:
            logger.warning("no status reported for %d earlier findings; omitting the progress line", total)

            return None

        fixed = min(sum(1 for finding in reported if finding.is_fixed), total)
        line = f"📊 Из прошлых замечаний исправлено: {fixed} из {total}."

        return line + (" Все замечания закрыты." if fixed == total else f" Осталось: {total - fixed}.")

    @staticmethod
    def _is_re_review(context: ReviewContextDTO | None) -> bool:
        return context is not None and bool(context.findings)

    @classmethod
    def _sign_inline_review(
        cls,
        review: ReviewResponseDTO,
        context: ReviewContextDTO | None,
    ) -> ReviewResponseDTO:
        """Headline and sign the review, and sign every inline comment in it.

        The signature is what lets a later review tell ReVu's own words from the
        author's, which matters most when both use the same account.
        """
        progress = cls._progress_line(review, context)
        lines = [review_marker.header(re_review=cls._is_re_review(context))]
        lines.extend(line for line in (progress, review.general_comment) if line)
        comments = [replace(comment, body=review_marker.sign_inline(comment.body)) for comment in review.comments]

        return replace(review, general_comment=review_marker.mark("\n".join(lines)), comments=comments)

    @staticmethod
    def _sign_summary(text: str, context: ReviewContextDTO | None) -> str:
        """Comment mode publishes one comment; the model reports progress in its text."""
        header = review_marker.header(re_review=ReviewRunner._is_re_review(context))

        return review_marker.mark(f"{header}\n\n{text}")

    async def _fetch_code_context(
        self,
        reader: GitReaderProtocol,
        config: GitConnectionConfig,
        request: ReviewRequest,
        diff: str,
    ) -> CodeContextDTO:
        """The surrounding code, plus the numbers that let the budgets be tuned.

        The builder never raises: a review that cannot read its context still runs,
        with fewer entries and a reason recorded in the stats.
        """
        context_request = ContextRequest(
            repo=request.repo,
            revision=request.revision,
            diff=diff,
            depth=config.context_depth,
            max_extra_files=config.context_max_files,
            max_chars=config.context_max_chars,
        )

        context = await self._context_builder.build(reader, context_request)
        self._log_context(config, request, diff, context)

        return context

    @staticmethod
    def _log_context(
        config: GitConnectionConfig,
        request: ReviewRequest,
        diff: str,
        context: CodeContextDTO,
    ) -> None:
        """One line per review.

        Deliberately verbose: the budgets are guesses until an operator reads real
        runs and sees what the diff cost against what the context added.
        """
        stats = context.stats
        degraded = f" degraded={stats.degraded}" if stats.degraded else ""

        logger.info(
            "review context for connection %s, %s#%s: depth=%s; "
            "diff=%d files/%d chars (~%d tokens); "
            "context=%d entries/%d chars (~%d tokens): bodies=%d extra_files=%d "
            "signatures=%d tests=%d unparsed=%d; requests=%d truncated=%s took=%.2fs%s",
            config.key,
            request.repo,
            request.number,
            stats.depth,
            stats.changed_files,
            len(diff),
            len(diff) // CHARS_PER_TOKEN,
            len(context.entries),
            stats.chars,
            stats.chars // CHARS_PER_TOKEN,
            stats.body_files,
            stats.extra_files,
            stats.signatures,
            stats.tests,
            stats.unparsed_files,
            stats.requests,
            stats.truncated,
            stats.seconds,
            degraded,
        )

    @staticmethod
    def annotate_diff(diff_text: str) -> str:
        """Rewrite a unified diff with the line numbers of both sides.

        The model cannot be expected to count lines in a hunk, but an inline comment
        needs an exact line; annotating is cheaper and more reliable than asking it
        to derive them.
        """
        patch = PatchSet(diff_text)
        out: list[str] = []

        for f in patch:
            src = f.source_file
            dst = f.target_file

            out.append(f"diff --git {src} {dst}")

            if getattr(f, "is_added_file", False) or getattr(f, "is_new_file", False):
                out.append("new file mode 100644")
            if getattr(f, "is_removed_file", False):
                out.append("deleted file mode 100644")

            out.append(f"--- {src}")
            out.append(f"+++ {dst}")

            for h in f:
                src_len = h.source_length or 0
                dst_len = h.target_length or 0
                out.append(f"@@ -{h.source_start},{src_len} +{h.target_start},{dst_len} @@")

                old_ln = h.source_start
                new_ln = h.target_start

                for ln in h:
                    text = ln.value.rstrip("\n")

                    if ln.is_context:
                        out.append(f"  [{old_ln}->{new_ln}] {text}")
                        old_ln += 1
                        new_ln += 1
                    elif ln.is_removed:
                        out.append(f"- [{old_ln}] {text}")
                        old_ln += 1
                    elif ln.is_added:
                        out.append(f"+ [{new_ln}] {text}")
                        new_ln += 1

        return "\n".join(out)
