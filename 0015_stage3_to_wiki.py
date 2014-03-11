#!/usr/bin/env python

import sys
import envoy
from ost.utils import confluence2

SPACE = 'PROJ'
PAGE = '0015-3 tracking'

report = envoy.run('0015_stage3_rep.py')

if report.status_code == 0:
    wiki = confluence2.connect()
    new_content = wiki.convert_wiki_to_storage(report.std_out)
    wiki.replace_page_content(SPACE, PAGE, new_content)
else:
    print 'Script failed:'
    print report.std_out
    print report.std_err
    sys.exit(1)
