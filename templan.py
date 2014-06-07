#!/usr/bin/env python

from __future__ import print_function

import click
import collections
import re
import envoy

from ost.utils import confluence2


class Context(object):
    """Container for the template data."""

    sig_filter = ''

    def get_invocations(self):
        if not hasattr(self, 'invocations'):
            self.invocations = collections.defaultdict(list)
            rxp = re.compile(r"\.\/([^:]+):[^\(]+\('(\w+)', (.*)\)")
            r = envoy.run("grep -r 'message_router.render' .")
            for line in r.std_out.split('\n'):
                m = rxp.match(line)
                if m:
                    file, template, signature = m.groups()
                    self.invocations[template].append((file, signature))
        return self.invocations

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
            for t_name in self.get_references():
                if not [inv for inv in self.get_invocations()[t_name]
                        if self.sig_filter in inv[1]]:
                    continue
                self.summary[t_name] = {
                    'template': t_name,
                    'references': sorted(self.references[t_name]),
                    'invocations': sorted(self.invocations[t_name])
                }
        return self.summary

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
def cli(context, sig, refs):
    """Script for analyzing e-mail templates in Accreditation."""
    context.sig_filter = sig
    context.include_refs = refs


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
def print(context, html):
    """Print the summary to the screen."""
    if html:
        click.echo(context.summary_table())
    else:
        for t_name, t_info in sorted(context.get_summary().items()):
            click.echo('[%s]' % t_name)
            for inv in t_info['invocations']:
                click.echo(' inv: %s (%s)' % inv)
            if context.include_refs:
                for ref in t_info['references']:
                    click.echo(' var: %s' % ref)

if __name__ == '__main__':
    cli()
