from locale import strcoll


PREFIX = {
    'CONTEXT': ' ',
    'ADDED': '+',
    'REMOVED': '-'
}


def json_diff_to_unified(diff_json) -> str:
    lines = []
    for file_diff in diff_json['diffs']:
        src = file_diff['source']['toString']
        dst = file_diff['destination']['toString']
        lines.append(f"diff --git a/{src} b/{dst}")
        lines.append(f'--- a/{src}')
        lines.append(f'+++ b/{dst}')
        
        for hunk in file_diff['hunks']:
            src_start = hunk['sourceLine']
            src_span = hunk['sourceSpan']
            dst_start = hunk['destinationLine']
            dst_span = hunk['destinationSpan']
            lines.append(f"@@ -{src_start},{src_span} + {dst_start},{dst_span} @@")
            
            for segment in hunk['segments']:
                prefix = PREFIX[segment['type']]
                for line in segment['lines']:
                    lines.append(f"{prefix}{line['line']}")
    return '\n'.join(lines)
