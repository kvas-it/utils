#!/usr/bin/env python
"""
Report on accreditation Stage 3.
"""

from __future__ import print_function

import datetime

from ost.utils.jira_version_report import VersionReport, connect
from ost.utils.jira_charts import TimeBurndownChart


PROJECT = 'ACCRWF'
VERSION = '3.0'

week = datetime.timedelta(7)
day = datetime.timedelta(1)
today = datetime.datetime.today()

weekly = [datetime.datetime(2014, 3, 10) + week * i for i in range(15)]
weekly = [w for w in weekly if w < today]

start_of_week = datetime.datetime(*(today -
        day * today.weekday()).timetuple()[:3] + (20, 00))
last_week = [start_of_week + day * i for i in range(5)]
last_week = [d if d < today else d - day * 7 for d in last_week]
last_week = sorted(last_week)


query = (VersionReport(connect())
        .search_project_version(PROJECT, VERSION)
        .filter(lambda issue: issue['status']
                not in [u'Deprecated', u'Replaced'])
        .add_linked_issues(['implemented_by']))

tbc = TimeBurndownChart(query.add_subtasks())

print('h2. Charts\n')
print('h3. Last week\n')
print(tbc.to_wiki_markup(last_week, width=700))

if len(weekly) > 1:
    print('h3. All stage by week\n')
    print(tbc.to_wiki_markup(weekly, width=700))

print('\nh2. Requirements and tasks details\n')
print(query.aggregate_attribute('time_progress', lambda *t: sum(t[1:]))
        .aggregate_attribute('time_total', lambda *t: sum(t[1:]))
        .sort_by_status().paint_status()
        .to_wiki_markup())
