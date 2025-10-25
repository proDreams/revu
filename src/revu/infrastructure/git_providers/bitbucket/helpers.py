def json_diff_to_unified(diff_json) -> str:
    prefix_replacer = {"CONTEXT": " ", "ADDED": "+", "REMOVED": "-"}
    lines = []
    for file_diff in diff_json["diffs"]:
        src = (file_diff.get("source") or {}).get("toString", "/dev/null")
        dst = (file_diff.get("destination") or {}).get("toString", "/dev/null")
        lines.append(f"diff --git a/{src} b/{dst}")

        lines.append(f"--- a/{src}")
        lines.append(f"+++ b/{dst}")

        for hunk in file_diff["hunks"]:
            src_start = hunk["sourceLine"]
            src_span = hunk["sourceSpan"]
            dst_start = hunk["destinationLine"]
            dst_span = hunk["destinationSpan"]
            lines.append(f"@@ -{src_start},{src_span} +{dst_start},{dst_span} @@")

            for segment in hunk["segments"]:
                prefix = prefix_replacer[segment["type"]]
                for line in segment["lines"]:
                    lines.append(f"{prefix}{line.get('line', '')}")
    return "\n".join(lines)
