from py_markdown_table.markdown_table import markdown_table

def md_lines(*args):
	recs = lambda arg: arg if isinstance(arg,str) else ( md_lines(*arg) if isinstance(arg, list) else str(arg) )
	return '\n\n'.join([recs(a) for a in args])

def md_expand(summary, inner):
	return ['<details>','<summary>', summary, '</summary>', inner, '</details>']

def md_table(data):
	if len(data) == 0:
		return ''
	return markdown_table(data).set_params(row_sep = 'markdown', padding_weight='right', quote = False).get_markdown()
