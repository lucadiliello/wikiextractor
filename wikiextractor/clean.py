import html
import logging
import re
import time
from html.entities import name2codepoint

from wikiextractor.regex import (ExtLinkBracketedRegex, MagicWords, bold,
                                 bold_italic, comment, discardElements, dots,
                                 ignored_tag_patterns, italic, italic_quote,
                                 listClose, magic_words_regex,
                                 placeholder_tag_patterns, quote_quote,
                                 section, selfClosing_tag_patterns, spaces,
                                 syntax_highlight_regex, tail_regex)


def clean(extractor, text):
    """
    Transforms wiki markup. If the command line flag --escape_doc is set then the text is also escaped
    @see https://www.mediawiki.org/wiki/Help:Formatting
    """

    # Drop transclusions (template, parser functions)
    text = dropNested(text, r'{{', r'}}')

    # Drop tables
    text = dropNested(text, r'{\|', r'\|}')

    # replace external links
    text = replaceExternalLinks(text)

    # replace internal links
    text = replaceInternalLinks(text, extractor.args.acceptedNamespaces)

    # drop MagicWords behavioral switches
    text = magic_words_regex.sub('', text)

    # turn into HTML, except for the content of <syntaxhighlight>
    res = ''
    cur = 0
    for m in syntax_highlight_regex.finditer(text):
        end = m.end()
        res += unescape(text[cur:m.start()]) + m.group(1)
        cur = end
    text = res + unescape(text[cur:])

    text = bold_italic.sub(r'\1', text)
    text = bold.sub(r'\1', text)
    text = italic_quote.sub(r'"\1"', text)
    text = italic.sub(r'"\1"', text)
    text = quote_quote.sub(r'"\1"', text)

    # residuals of unbalanced quotes
    text = text.replace("'''", '').replace("''", '"')

    # Collect spans
    spans = []
    # Drop HTML comments
    for m in comment.finditer(text):
        spans.append((m.start(), m.end()))

    # Drop self-closing tags
    for pattern in selfClosing_tag_patterns:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end()))

    # Drop ignored tags
    for left, right in ignored_tag_patterns:
        for m in left.finditer(text):
            spans.append((m.start(), m.end()))
        for m in right.finditer(text):
            spans.append((m.start(), m.end()))

    # Bulk remove all spans
    text = dropSpans(spans, text)

    # Drop discarded elements
    for tag in discardElements:
        text = dropNested(text, r'<\s*%s\b[^>/]*>' % tag, r'<\s*/\s*%s>' % tag)

    text = unescape(text)

    # Expand placeholders
    for pattern, placeholder in placeholder_tag_patterns:
        index = 1
        for match in pattern.finditer(text):
            text = text.replace(match.group(), '%s_%d' % (placeholder, index))
            index += 1

    text = text.replace('<<', u'«').replace('>>', u'»')

    # Cleanup text
    text = text.replace('\t', ' ')
    text = spaces.sub(' ', text)
    text = dots.sub('...', text)
    text = re.sub(u' (,:\.\)\]»)', r'\1', text)
    text = re.sub(u'(\[\(«) ', r'\1', text)
    text = re.sub(r'\n\W+?\n', '\n', text, flags=re.U)  # lines with only punctuations
    text = text.replace(',,', ',').replace(',.', '.')
    if extractor.args.escape_doc:
        text = html.escape(text)
    return text


def compact(text, mark_headers=False):
    """
    Deal with headers, lists, empty sections, residuals of tables.
    :param text: convert to HTML
    """

    page = []  # list of paragraph
    headers = {}  # Headers for unfilled sections
    emptySection = False  # empty sections are discarded
    listLevel = ''  # nesting of lists

    for line in text.split('\n'):

        if not line:
            continue
        # Handle section titles
        m = section.match(line)

        if m:
            title = m.group(2)
            lev = len(m.group(1))

            if title and title[-1] not in '!?':
                title += '.'
            if mark_headers:
                title = "## " + title

            headers[lev] = title
            # drop previous headers
            headers = { k: v for k, v in headers.items() if k > lev }
            emptySection = True
            continue

        # Handle page title
        if line.startswith('++'):
            title = line[2:-2]
            if title:
                if title[-1] not in '!?':
                    title += '.'
                page.append(title)

        # handle indents
        elif line[0] == ':':
            # page.append(line.lstrip(':*#;'))
            continue

        # handle lists
        elif line[0] in '*#;:':
            continue

        elif len(listLevel):
            for c in reversed(listLevel):
                page.append(listClose[c])
            listLevel = []

        # Drop residuals of lists
        elif line[0] in '{|' or line[-1] == '}':
            continue
        
        # Drop irrelevant lines
        elif (line[0] == '(' and line[-1] == ')') or line.strip('.-') == '':
            continue
        
        elif len(headers):
            items = headers.items()
            items = sorted(items)
            for (i, v) in items:
                page.append(v)
            headers.clear()
            page.append(line)  # first line
            emptySection = False
        
        elif not emptySection:
            page.append(line)

    return page

def dropSpans(spans, text):
    """
    Drop from text the blocks identified in :param spans:, possibly nested.
    """
    spans.sort()
    res = ''
    offset = 0
    for s, e in spans:
        if offset <= s:  # handle nesting
            if offset < s:
                res += text[offset:s]
            offset = e
    res += text[offset:]
    return res

def dropNested(text, openDelim, closeDelim):
    """
    A matching function for nested expressions, e.g. namespaces and tables.
    """
    openRE = re.compile(openDelim, re.IGNORECASE)
    closeRE = re.compile(closeDelim, re.IGNORECASE)

    # partition text in separate blocks { } { }
    spans = []  # pairs (s, e) for each partition
    nest = 0  # nesting level
    start = openRE.search(text, 0)

    # if there is not nested block
    if not start:
        return text

    end = closeRE.search(text, start.end())
    next = start

    while end:
        next = openRE.search(text, next.end())
        if not next:  # termination
            while nest:  # close all pending
                nest -= 1
                end0 = closeRE.search(text, end.end())
                if end0:
                    end = end0
                else:
                    break
            spans.append((start.start(), end.end()))
            break
        while end.end() < next.start():
            # { } {
            if nest:
                nest -= 1
                # try closing more
                last = end.end()
                end = closeRE.search(text, end.end())
                if not end:  # unbalanced
                    if spans:
                        span = (spans[0][0], last)
                    else:
                        span = (start.start(), last)
                    spans = [span]
                    break
            else:
                spans.append((start.start(), end.end()))
                # advance start, find next close
                start = next
                end = closeRE.search(text, next.end())
                break  # { }
        if next != start:
            # { { }
            nest += 1

    # collect text outside partitions
    return dropSpans(spans, text)

def replaceExternalLinks(text):
    s = ''
    cur = 0
    for m in ExtLinkBracketedRegex.finditer(text):
        s += text[cur:m.start()]
        cur = m.end()
        s += m.group(3)
    return s + text[cur:]

def replaceInternalLinks(text, acceptedNamespaces):
    """
    Replaces external links of the form:
    [[title |...|label]]trail

    with title concatenated with trail, when present, e.g. 's' for plural.
    """
    # call this after removal of external links, so we need not worry about
    # triple closing ]]].
    cur = 0
    res = ''
    for s, e in findBalanced(text, ['[['], [']]']):
        m = tail_regex.match(text, e)
        if m:
            trail = m.group(0)
            end = m.end()
        else:
            trail = ''
            end = e
        inner = text[s + 2:e - 2]
        # find first |
        pipe = inner.find('|')
        if pipe < 0:
            title = inner
            label = title
        else:
            title = inner[:pipe].rstrip()
            # find last |
            curp = pipe + 1
            for s1, e1 in findBalanced(inner, ['[['], [']]']):
                last = inner.rfind('|', curp, s1)
                if last >= 0:
                    pipe = last  # advance
                curp = e1
            label = inner[pipe + 1:].strip()
        res += text[cur:s] + makeInternalLink(title, label, acceptedNamespaces) + trail
        cur = end
    return res + text[cur:]

def makeInternalLink(title, label, acceptedNamespaces):
    colon = title.find(':')
    if colon > 0 and title[:colon] not in acceptedNamespaces:
        return ''
    if colon == 0:
        # drop also :File:
        colon2 = title.find(':', colon + 1)
        if colon2 > 1 and title[colon + 1:colon2] not in acceptedNamespaces:
            return ''
    return label

def unescape(text):
    """
    Removes HTML or XML character references and entities from a text string.

    :param text The HTML (or XML) source text.
    :return The plain text, as a Unicode string, if necessary.
    """
    def fixup(m):
        text = m.group(0)
        code = m.group(1)
        try:
            if text[1] == "#":  # character reference
                if text[2] == "x":
                    return chr(int(code[1:], 16))
                else:
                    return chr(int(code))
            else:  # named entity
                return chr(name2codepoint[code])
        except:
            return text  # leave as is

    text = html.unescape(text)
    text = re.sub("&#?(\w+);", fixup, text)
    return text

class Extractor:
    """
    An extraction task on a article.
    """

    def __init__(self, args, id, title, page):
        """
        :param page: a list of lines.
        """
        self.args = args
        self.id = id
        self.title = title
        self.page = page
        self.magicWords = MagicWords()
        self.frame = []
        self.recursion_exceeded_1_errs = 0  # template recursion within expandTemplates()
        self.recursion_exceeded_2_errs = 0  # template recursion within expandTemplate()
        self.recursion_exceeded_3_errs = 0  # parameter recursion
        self.template_title_errs = 0

    def clean_text(self, text, mark_headers=False):
        """
        :param mark_headers: True to distinguish headers from paragraphs
          e.g. "## Section 1"
        """
        self.magicWords['pagename'] = self.title
        self.magicWords['fullpagename'] = self.title
        self.magicWords['currentyear'] = time.strftime('%Y')
        self.magicWords['currentmonth'] = time.strftime('%m')
        self.magicWords['currentday'] = time.strftime('%d')
        self.magicWords['currenthour'] = time.strftime('%H')
        self.magicWords['currenttime'] = time.strftime('%H:%M:%S')

        text = clean(self, text)

        text = compact(text, mark_headers=mark_headers)
        return text

    def extract(self, out):
        """
        :param out: a memory file.
        """
        logging.debug("%s\t%s", self.id, self.title)
        text = ''.join(self.page)

        header = ""
        footer = ""

        if self.args.keep_doc_tag:
            header += '<doc id="%s" title="%s">\n' % (self.id, self.title)
            # Separate header from text with a newline.
            header += self.title + '\n'

            footer = "\n</doc>\n"
            out.write(header)

        text = self.clean_text(text)

        if not self.args.keep_doc_tag:
            out.write(self.title.strip() + ". ")

        for line in text:
            line = line.strip()
            if len(line) > 0:
                out.write(line + "\n")
        out.write("\n")

        if self.args.keep_doc_tag:
            out.write(footer)

        errs = (self.template_title_errs,
                self.recursion_exceeded_1_errs,
                self.recursion_exceeded_2_errs,
                self.recursion_exceeded_3_errs)
        if any(errs):
            logging.warn("Template errors in article '%s' (%s): title(%d) recursion(%d, %d, %d)",
                         self.title, self.id, *errs)


def findBalanced(text, openDelim, closeDelim):
    """
    Assuming that text contains a properly balanced expression using
    :param openDelim: as opening delimiters and
    :param closeDelim: as closing delimiters.
    :return: an iterator producing pairs (start, end) of start and end
    positions in text containing a balanced expression.
    """
    openPat = '|'.join([re.escape(x) for x in openDelim])
    # patter for delimiters expected after each opening delimiter
    afterPat = {o: re.compile(openPat + '|' + c, re.DOTALL) for o, c in zip(openDelim, closeDelim)}
    stack = []
    start = 0
    cur = 0
    # end = len(text)
    startSet = False
    startPat = re.compile(openPat)
    nextPat = startPat
    while True:
        next = nextPat.search(text, cur)
        if not next:
            return
        if not startSet:
            start = next.start()
            startSet = True
        delim = next.group(0)
        if delim in openDelim:
            stack.append(delim)
            nextPat = afterPat[delim]
        else:
            opening = stack.pop()
            # assert opening == openDelim[closeDelim.index(next.group(0))]
            if stack:
                nextPat = afterPat[stack[-1]]
            else:
                yield start, next.end()
                nextPat = startPat
                start = next.end()
                startSet = False
        cur = next.end()
