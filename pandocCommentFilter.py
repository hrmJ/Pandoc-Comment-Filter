#!/usr/bin/env python

'''
Pandoc filter to extend the use of RawInline and RawBlocks to highlight 
or comment on text. In draft mode, both are displayed in red; in 
non-draft mode, only highlights are displayed, and that only in black.

Copyright (C) 2015 Bennett Helm 

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.


# Syntax Extensions

## Block-Level Items:

`<!comment>`: begin comment block (or speaker notes for revealjs)
`</!comment>`: end comment block (or speaker notes for revealjs)
`<!highlight>`: begin highlight block
`</!highlight>`: end highlight block
`<center>`: begin centering
`</center>`: end centering


## Inline Items:

`<comment>`: begin commenting
`</comment>`: end commenting
`<highlight>`: begin highlighting
`</highlight>`: end highlighting
`<fixme>`: begin FixMe margin note (and highlighting)
`</fixme>`: end FixMe margin note (and highlighting)
`<margin>`: begin margin note
`</margin>`: end margin note


## Other Items:

`< `: do not indent paragraph (used after quotation block)
`<l LABEL>`: create a label
`<r LABEL>`: create a reference
`<rp LABEL>`: create a page reference


## Images: Allow for tikZ figures in code blocks. They should have the following format:

~~~ {#tikz caption='Caption' id='fig:id' tikzlibrary='items,to,go,in,\\usetikzlibrary{}'}

[LaTeX code]

~~~

'''

from pandocfilters import toJSONFilter, RawInline, Para, Plain, Image, Str
from os import path, mkdir, chdir, getcwd
from shutil import copyfile, rmtree
from sys import getfilesystemencoding, stderr
from tempfile import mkdtemp
from subprocess import call
from hashlib import sha1

IMAGE_PATH = '/Users/bennett/tmp/pandoc/Figures'

blockStatus = []
inlineStatus = []

colors = {
	'<!comment>': 'red', 
	'<comment>': 'red', 
	'<!highlight>': 'magenta', 
	'<highlight>': 'magenta',
	'<margin>': 'red',
	'<fixme>': 'cyan',
}
endColor = '\\color{black}{}'
marginStyle = 'max-width:20%; border: 1px solid black; padding: 1ex; margin: 1ex; float:right; font-size: small;' # HTML style for margin notes

latexText = {
	'<!comment>': '\\color{' + colors['<!comment>'] + '}{}',
	'</!comment>': endColor,
	'<!highlight>': '\\color{' + colors['<!highlight>'] + '}{}',
	'</!highlight>': endColor,
	'<comment>': '\\color{' + colors['<comment>'] + '}{}',
	'</comment>': '',
	'<highlight>': '\\color{' + colors['<highlight>'] + '}{}',
	'</highlight>': '',
	'<margin>': '\\marginpar{\\footnotesize{\\color{' + colors['<margin>'] + '}{}',
	'</margin>': '}}',
	'<fixme>': '\\marginpar{\\footnotesize{\\color{' + colors['<fixme>'] + '}{}Fix this!}}\\color{' + colors['<fixme>'] + '}{}',
	'</fixme>': '',
	'<center>': '\\begin{center}',
	'</center>': '\\end{center}',
	'<end>': endColor
}
htmlText = {
	'<!comment>': '<div style="color: ' + colors['<!comment>'] + ';">',
	'</!comment>': '</div>',
	'<!highlight>': '<div style="color: ' + colors['<!highlight>'] + ';">',
	'</!highlight>': '</div>',
	'<comment>': '<span style="color: ' + colors['<comment>'] + ';">',
	'</comment>': '</span>',
	'<highlight>': '<span style="color: ' + colors['<highlight>'] + ';">',
	'</highlight>': '</span>',
	'<margin>': '<span style="color: ' + colors['<margin>'] + '; ' + marginStyle + '">',
	'</margin>': '</span>',
	'<fixme>': '<span style="color: ' + colors['<fixme>'] + '; ' + marginStyle + '">Fix this!</span><span style="color: ' + colors['<fixme>'] + ';">',
	'</fixme>': '</span>',
	'<center>': '', # TODO Add this!
	'</center>': '' # TODO Here too!
}
revealjsText = {
	'<!comment>': '<aside class="notes">',
	'</!comment>': '</aside>'
}

marginStatus = False # Whether currently in a margin note or not
# TODO: Get rid of marginStatus (put into inlineStatus)!

def my_sha1(x):
	return sha1(x.encode(getfilesystemencoding())).hexdigest()

def tikz2image(tikz, filetype, outfile, library):
	tmpdir = mkdtemp()
	olddir = getcwd()
	chdir(tmpdir)
	f = open('tikz.tex', 'w')
	f.write('\\documentclass{standalone}\n\\usepackage{tikz}\n')
	if library: f.write('\\usetikzlibrary{' + library + '}\n')
	f.write('\\begin{document}\n')
	f.write(tikz)
	f.write('\n\\end{document}\n')
	f.close()
	p = call(['pdflatex', 'tikz.tex'], stdout=stderr)
	chdir(olddir)
	if filetype == 'pdf':
		copyfile(path.join(tmpdir, 'tikz.pdf'), outfile + '.' + filetype)
	else:
		call(['convert', path.join(tmpdir, 'tikz.pdf'), outfile + '.' + filetype])
	rmtree(tmpdir)

def latex(text):
	return RawInline('latex', text)

def html(text):
	return RawInline('html', text)
	
def closeHtmlSpan(oldInlineStatus):
	if oldInlineStatus in ['<comment>', '<highlight>', '<fixme>']: return '</span>'
	else: return ''

def closeHtmlDiv(oldBlockStatus):
	if oldBlockStatus in ['<!comment>', '<!highlight>']: return '</div>'
	else: return ''

def handle_comments(key, value, format, meta):
	global blockStatus, blockColor, inlineStatus, marginStatus
	
	# If translating to markdown, leave everything alone.
	if format == 'markdown': return
	
#	# Keep track of this for later....
	oldInlineStatus = inlineStatus # TODO Delete this line!

	# Get draft status from metadata field (or assume not draft if there's no such field)
	try: draft = meta['draft']['c']
	except KeyError: draft = False

	# First check to see if we're changing blockStatus...
	if key == 'RawBlock':
		type, tag = value
		if type != 'html': pass
		tag = tag.lower()
		if tag in ['<!comment>', '<!highlight>']:
			if blockStatus: oldBlockStatus = blockStatus[-1]
			else: oldBlockStatus = ''
			blockStatus.append(tag)
			if not draft and format != 'revealjs': return []
			elif format == 'latex':
				return Para([latex(latexText[tag])])
			elif format == 'html' or (format == 'revealjs' and tag == '<!highlight>'):
				return Plain([html(closeHtmlDiv(oldBlockStatus) + htmlText[tag])])
			elif format == 'revealjs': # tag == '<!comment>', so make speaker note
				return Plain([html(closeHtmlDiv(oldBlockStatus) + revealjsText[tag])])
			else: return []
			
		elif tag in ['</!comment>', '</!highlight>']:
			currentBlockStatus = blockStatus.pop()
			if currentBlockStatus[1:] == tag[2:]: # If we have a matching closing tag...
				if not draft: return []
				if blockStatus: tag = blockStatus[-1] # Switch back to previous
				if format == 'latex':
					return Para([latex(latexText[tag])])
				elif format == 'html' or (format == 'revealjs' and tag == '<!highlight>'):
					return Plain([html(htmlText[tag])])
				elif format == 'revealjs':
					return Plain([html(revealjsText[tag])])
				else: return []
			else: exit(1) # TODO Is this right?
			
		elif tag == '<center>':
			blockStatus.append(tag)
			if format in ['latex', 'beamer']: return Para([latex(latexText[tag])])
			elif format == 'html': return # TODO Fix centering in html
	
		elif tag == '</center>':
			currentBlockStatus = blockStatus.pop()
			if currentBlockStatus[1:] == tag[2:]:
				if format in ['latex', 'beamer']: return Para([latex(latexText[tag])])
				elif format == 'html': return # TODO Fix centering in html
			else: exit(1) # TODO Is this right?
		
	# Then check to see if we're changing inlineStatus...
	elif key == 'RawInline':
		type, tag = value
		if type != 'html': pass
		tag = tag.lower()
		
		if tag in ['<margin>', '<comment>', '<highlight>', '<fixme>']:
			if inlineStatus: oldInlineStatus == inlineStatus[-1]
			else: oldInlineStatus == ''
			inlineStatus.append(tag)
			if not draft: return []
			elif format in ['latex', 'beamer']:
				return latex(latexText[tag])
			elif format in ['html', 'revealjs']:
				return html(closeHtmlSpan(oldInlineStatus) + htmlText[tag])
			else: return []
		
		elif tag in ['</margin>', '</comment>', '</highlight>', '</fixme>']:
			currentInlineStatus = inlineStatus.pop()
			if currentInlineStatus[1:] == tag[2:]: # If we have a matching closing tag...
				if not draft: return []
				if tag == '</margin>': closeText = latexText[tag] # Only need to close previous inline if margin.
				else: closeText = ''
				if inlineStatus: newTag = inlineStatus[-1] # Switch back to previous
				else: newTag = '<end>'
				if format in ['latex', 'beamer']:
					return latex(closeText + latexText[newTag])
				elif format in ['html', 'revealjs']: return html(htmlText[tag])
			else: exit(1) # TODO Is this right?
		
		elif tag.startswith('<l ') and tag.endswith('>'): # My definition of a label
			label = tag[3:-1]
			if format == 'latex': return latex('\\label{' + label + '}')
			elif format == 'html': return html('<a name="' + label + '">')
			
		elif tag.startswith('<r ') and tag.endswith('>'): # My definition of a reference
			label = tag[3:-1]
			if format == 'latex': return latex('\\cref{' + label + '}')
			elif format == 'html': return html('<a href="#' + label + '">here</a>')
			
		elif tag.startswith('<rp ') and tag.endswith('>'): # My definition of a page reference
			label = tag[4:-1]
			if format == 'latex': return latex('\\cpageref{' + label + '}')
			elif format == 'html': return html('<a href="#' + label + '">here</a>')
	
	
	# If translating to LaTeX, beginning a paragraph with '<' will cause 
	# '\noindent{}' to be output first.
	elif key == 'Para':
		try:
			if value[0]['t'] == 'Str' and value[0]['c'] == '<' and value[1]['t'] == 'Space': 
				if format == 'latex': return Para([latex('\\noindent{}')] + value[2:])
				else: return Para(value[2:])
		except: pass # May happen if the paragraph is empty.
	
	
	# Check for tikz CodeBlock. If it exists, try typesetting figure
	elif key == 'CodeBlock':
		(id, classes, attributes), code = value
		if 'tikz' in classes or '\\begin{tikzpicture}' in code:
			outfile = path.join(IMAGE_PATH, my_sha1(code))
			if format == 'html': filetype = 'png'
			if format == 'latex': filetype = 'pdf'
			else: filetype = 'png'
			sourceFile = outfile + '.' + filetype
			caption = ''
			id = ''
			library = ''
			for a, b in attributes:
				if a == 'caption': caption = b
				elif a == 'id': id = '{#' + b + '}'
				elif a == 'tikzlibrary': library = b
			if not path.isfile(sourceFile):
				try:
					mkdir(IMAGE_PATH)
					stderr.write('Created directory ' + IMAGE_PATH + '\n')
				except OSError: pass
				tikz2image(code, filetype, outfile, library)
				stderr.write('Created image ' + sourceFile + '\n')
			if id:
				return Para([Image([Str(caption)], [sourceFile, caption]), Str(id)])
			else:
				return Para([Image([Str(caption)], [sourceFile, caption])])

	
	# Check for images and copy/convert to IMAGE_PATH
# 	elif key == 'Image':
# 		c, f = value
# 		caption = c[0]['c']
# 		imageFile, label = f
# 		newImageFile = copyImage(imageFile, format)
# 		return Image([Str(caption)], [newImageFile, label])
	
	
	# Finally, if we're not in draft mode and we're reading a block comment or 
	# an inline comment or margin note, then suppress output.
	elif '<!comment>' in blockStatus and not draft and format != 'revealjs': return []
	elif '<comment>' in inlineStatus and not draft: return []
	elif '<margin>' in inlineStatus and not draft: return[]


if __name__ == "__main__":
  toJSONFilter(handle_comments)
