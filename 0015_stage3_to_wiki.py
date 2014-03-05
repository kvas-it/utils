#!/usr/bin/env python

import sys
import envoy
from ost.utils import confluence1

SPACE = 'PROJ'
PAGE = '0015 - Stage 2 tracking'

report = envoy.run('0015_stage2_report')

if report.status_code == 0:
    wiki = confluence1.connect()
    wiki.replace_page_content(SPACE, PAGE, report.std_out)
else:
    print 'Script failed:'
    print report.std_out
    print report.std_err
    sys.exit(1)
