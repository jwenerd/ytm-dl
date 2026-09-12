from py_markdown_table.markdown_table import markdown_table


def md_lines(*args):
    def recs(arg):
        if isinstance(arg, str):
            return arg
        if isinstance(arg, list):
            return md_lines(*arg)
        return str(arg)

    return "\n\n".join([recs(a) for a in args])


def md_expand(summary, inner):
    return ["<details>", "<summary>", summary, "</summary>", inner, "</details>"]


def md_table(data):
    if len(data) == 0:
        return ""
    return (
        markdown_table(data)
        .set_params(row_sep="markdown", padding_weight="right", quote=False)
        .get_markdown()
    )
