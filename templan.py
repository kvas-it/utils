#!/usr/bin/env python

from __future__ import print_function

import csv
import os
import click
import collections
import re
import envoy
import StringIO

from xml.etree import ElementTree as ET
from ost.utils import confluence2


class Context(object):
    """Container for the template data."""

    sig_filter = ''
    titles_file = ''

    def get_invocations(self):
        if not hasattr(self, 'invocations'):
            self.invocations = collections.defaultdict(list)
            rxp = re.compile(r"\.\/([^:]+):[^\(]+\('(\w+)', (.*)\)")
            r = envoy.run("grep -r 'message_router.render' .")
            for line in r.std_out.split('\n'):
                m = rxp.match(line)
                if m:
                    file, template, signature = m.groups()
                    if '.hg/' in file: continue
                    self.invocations[template].append((file, signature))
        return self.invocations

    def get_mt_references(self):
        if not hasattr(self, 'mt_references'):
            self.mt_references = collections.defaultdict(set)
        return self.mt_references

    def get_references(self):
        if not hasattr(self, 'references'):
            self.references = collections.defaultdict(set)
            rxp1 = re.compile(r"[^:]*/([^:/]+).dtml:(.*)")
            rxp2 = re.compile(r'expr="([^"]+)"')
            r = envoy.run("grep -r '<dtml-' faces/MessageTemplates")
            for line in r.std_out.split('\n'):
                m = rxp1.match(line)
                if m:
                    template, frag = m.groups()
                    s = rxp2.finditer(frag)
                    if s:
                        for m in s:
                            self.references[template].add(m.groups()[0])
        return self.references

    def get_summary(self):
        if not hasattr(self, 'summary'):
            self.summary = {}
            for t_name in set(self.get_references().keys() +
                              self.get_invocations().keys()):
                if not [inv for inv in self.get_invocations()[t_name]
                        if self.sig_filter in inv[1]]:
                    continue
                self.summary[t_name] = {
                    'template': t_name,
                    'references': sorted(self.references[t_name]),
                    'invocations': sorted(self.invocations[t_name])
                }
        return self.summary

    def get_titles(self):
        if not hasattr(self, 'titles'):
            self.titles = {}
            if self.titles_file:
                with open(self.titles_file) as tf:
                    for line in csv.reader(tf):
                        if len(line) > 1 and line[0] and line[1]:
                            self.titles[line[1]] = line[0]
        return self.titles

    def summary_table_csv(self):
        output = StringIO.StringIO()
        csvw = csv.writer(output)

        for t_name, t_info in sorted(self.get_summary().items()):
            t_inv = sorted(t_info['invocations'])
            for inv_file, inv_sig in t_inv:
                csvw.writerow([t_name, inv_file, inv_sig])

        return output.getvalue()

    def summary_table(self):
        rows = ["""    <tr>
        <th>Template</th>
        <th>Variable references</th>
        <th>Called from</th>
        <th>Call signature</th>
    </tr>"""]

        first_row = """    <tr>
        <td rowspan="{inv_count}">{t_name}</td>
        <td rowspan="{inv_count}">{t_refs}</td>
        <td>{inv_file}</td>
        <td>{inv_sig}</td>
    </tr>"""

        other_row = """    <tr>
        <td>{inv_file}</td>
        <td>{inv_sig}</td>
    </tr>"""

        noinv_row = """    <tr>
        <td>{t_name}</td>
        <td>{t_refs}</td>
        <td colspan="2">not called from python code</td>
    </tr>"""

        table = """<table>\n{rows}\n</table>"""

        for t_name, t_info in sorted(self.get_summary().items()):
            t_refs = '<br/>\n'.join(sorted(t_info['references']))
            t_inv = sorted(t_info['invocations'])
            if t_inv:
                inv_file, inv_sig = t_inv[0]
                inv_count = len(t_inv)
                rows.append(first_row.format(**locals()))
                for inv_file, inv_sig in t_inv[1:]:
                    rows.append(other_row.format(**locals()))
            else:
                rows.append(noinv_row.format(**locals()))

        return table.format(rows='\n'.join(rows))


pass_context = click.make_pass_decorator(Context, ensure=True)


@click.group()
@pass_context
@click.option('--sig', default='', help='Filter by signature')
@click.option('--refs', is_flag=True,
        help='Include variable references information')
@click.option('--titles-file', default='',
        help='CSV file containing template titles')
def cli(context, sig, refs, titles_file):
    """Script for analyzing e-mail templates in Accreditation."""
    context.sig_filter = sig
    context.include_refs = refs
    context.titles_file = titles_file


@cli.command()
@pass_context
@click.option('--space', default='SYS', help='Wiki space to use')
@click.option('--page', default='Template use summary',
        help='Wiki page to write')
def post(context, space, page):
    """Post the summary table to the wiki."""
    click.echo('Generating the summary table')
    table = context.summary_table()
    click.echo('Posting to confluence: [%s] %s' % (space, page))
    wiki = confluence2.connect()
    wiki.replace_page_content(space, page, table)
    click.echo('Done')


@cli.command()
@pass_context
@click.option('--html', is_flag=True, help='HTML output')
@click.option('--csv', is_flag=True, help='CSV output')
def print(context, html, csv):
    """Print the summary to the screen."""
    if html:
        click.echo(context.summary_table(), nl=False)
    elif csv:
        click.echo(context.summary_table_csv(), nl=False)
    else:
        tmpl_count = 0
        inv_count = 0
        for t_name, t_info in sorted(context.get_summary().items()):
            click.echo('[%s]' % t_name)
            tmpl_count += 1
            for inv in t_info['invocations']:
                click.echo(' inv: %s (%s)' % inv)
                inv_count += 1
            if context.include_refs:
                for ref in t_info['references']:
                    click.echo(' var: %s' % ref)

        click.echo('\nTemplates: %d, Invocations: %d' %
                (tmpl_count, inv_count))


class Convertor(object):
    """Converts dtml templates to mailplator templates."""

    def __init__(self, dtml_root, mp_root):
        self.dtml_root = dtml_root
        self.mp_root = mp_root

    def read(self, t_name):
        """Read the dtml template."""
        with open(os.path.join(self.dtml_root, t_name + '.dtml')) as fp:
            return fp.read()

    def write(self, t_name, content):
        """Write mpt template."""
        with open(os.path.join(self.mp_root, t_name + '.mpt'), 'w') as fp:
            fp.write(content)

    def convert(self, t_name):
        """Convert one templates."""
        def convert_close(match):
            type = match.group(1)
            if type.startswith('in'):
                return '{end for}'
            elif type.startswith('if'):
                return '{end if}'

        def convert_open(match):
            type = match.group(1)
            if type == 'var':
                return '{' + match.group(3) + '}'
            elif type == 'if':
                return '{if ' + match.group(3) + '}'
            elif type == 'in':
                return '{for %s_item in %s}' % (match.group(5), match.group(3))
            elif type in ['nmime', 'nboundary']:
                return ''
            else:
                raise ValueError(match.groups(0))

        dtml = self.read(t_name)
        # <dtml-var expr="form.title_or_id()">
        mpt = re.sub(r'</dtml-([^>]+)>', convert_close,
                re.sub(r'<dtml-(\w+)\s*(expr="([^"]+)")?'
                       r'(\s*prefix="([^"]+)")?[^>]*>',
                    convert_open, dtml))
        # click.echo(mpt)
        self.write(t_name, mpt)


@cli.command()
@pass_context
def convert(context):
    """Convert dtml templates to mailplator templates."""
    convertor = Convertor('faces/MessageTemplates', 'maint/message_templates')

    for t_name, t_info in sorted(context.get_summary().items()):
        click.echo('converting %s' % t_name)
        convertor.convert(t_name)


@cli.command()
@pass_context
def manifest(context):
    """Create manifest.xml for template list."""
    manifest = ET.Element('manifest')

    for t_name, t_info in sorted(context.get_summary().items()):
        if t_name in ('AppealRep', 'NewStat'):
            continue
        sig = t_info['invocations'][0][1]
        if t_name.startswith('Team'):
            type_name = 'team_template'
        elif t_name.endswith('PAInit'):
            type_name = 'pa_start_template'
        elif sig.startswith('activity'):
            if 'action' in sig:
                type_name = 'activity_action_template'
            else:
                type_name = 'activity_template'
        elif sig.startswith('completeness'):
            type_name = 'activity_completeness_template'
        elif sig.startswith('cycle'):
            if 'member' in sig:
                if 'action' in sig:
                    type_name = 'cycle_team_template'
                else:
                    type_name = 'cycle_teammember_template'
            else:
                type_name = 'cycle_template'
        elif sig.startswith('form'):
            if t_name.startswith('Subm'):
                type_name = 'form_template'
            else:
                type_name = 'review_template'

        ET.SubElement(manifest, 'template', file=t_name + '.mpt',
                type=type_name, id=t_name,
                title=context.get_titles().get(t_name, t_name))

    click.echo(ET.tostring(manifest))


if __name__ == '__main__':
    cli()
