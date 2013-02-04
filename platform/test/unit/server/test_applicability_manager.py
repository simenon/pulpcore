#!/usr/bin/python
#
# Copyright (c) 2012 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

import base
import mock_plugins

from mock import Mock
from pulp.plugins.loader import api as plugins
from pulp.server.db.model.criteria import Criteria
from pulp.server.db.model.consumer import Consumer, UnitProfile
from pulp.plugins.conduits.profiler import ProfilerConduit
from pulp.plugins.model import ApplicabilityReport
from pulp.server.managers import factory as factory
from pulp.server.exceptions import PulpExecutionException

# -- test cases ---------------------------------------------------------------

class ApplicabilityManagerTests(base.PulpServerTests):

    CONSUMER_IDS = ['test-1', 'test-2']
    FILTER = {'id':{'$in':CONSUMER_IDS}}
    SORT = [{'id':1}]
    CONSUMER_CRITERIA = Criteria(filters=FILTER, sort=SORT)
    REPO_CRITERIA = None
    PROFILE = [{'name':'zsh', 'version':'1.0'}, {'name':'ksh', 'version':'1.0'}]

    def setUp(self):
        base.PulpServerTests.setUp(self)
        Consumer.get_collection().remove()
        UnitProfile.get_collection().remove()
        plugins._create_manager()
        mock_plugins.install()
        profiler, cfg = plugins.get_profiler_by_type('rpm')
        profiler.units_applicable = \
            Mock(side_effect=lambda i,r,t,u,c,x:
                 [ApplicabilityReport(u, 'mysummary', 'mydetails')])

    def tearDown(self):
        base.PulpServerTests.tearDown(self)
        Consumer.get_collection().remove()
        UnitProfile.get_collection().remove()
        mock_plugins.reset()

    def populate(self):
        manager = factory.consumer_manager()
        for id in self.CONSUMER_IDS:
            manager.register(id)
        manager = factory.consumer_profile_manager()
        for id in self.CONSUMER_IDS:
            manager.create(id, 'rpm', self.PROFILE)

    def test_applicability(self):
        # Setup
        self.populate()
        # Test
        units = {'rpm': [{'name':'zsh', 'version':'2.0'},
                         {'name':'ksh', 'version':'2.0'}],
                 'mock-type': [{'name':'abc'},
                               {'name':'def'}]
                }
        report_units = [{'name':'zsh', 'version':'2.0'},
                        {'name':'ksh', 'version':'2.0'},
                        {'name': 'abc'},
                        {'name': 'def'}]
        
        rpm_units = [[{'name':'zsh', 'version':'2.0'},{'name':'ksh', 'version':'2.0'}]]

        manager = factory.consumer_applicability_manager()
        applicability = manager.units_applicable(consumer_criteria=self.CONSUMER_CRITERIA,
                                                 repo_criteria=self.REPO_CRITERIA, 
                                                 units=units)
        # verify
        self.assertEquals(len(applicability), 2)
        for id in self.CONSUMER_IDS:
            for type_id, report_list in applicability[id].items():
                # Check for rpm profiler and valid applicability
                for report in report_list:
                    if report.unit in report_units[0:2]:
                        self.assertEquals(report.summary, 'mysummary')
                        self.assertEquals(report.details, 'mydetails')
                        continue
                    # Check for mock-type profiles and invalid applicability
                    if report.unit in report_units[2:4]:
                        self.assertEquals(report.summary, 'mocked')
                        self.assertEquals(report.details, None)
                        continue

        profiler, cfg = plugins.get_profiler_by_type('rpm')
        call = 0
        args = [c[0] for c in profiler.units_applicable.call_args_list]
        for id in self.CONSUMER_IDS:
            for unit in rpm_units:
                self.assertEquals(args[call][0].id, id)
                self.assertEquals(args[call][0].profiles, {'rpm':self.PROFILE})
                self.assertEquals(args[call][1], [])
                self.assertEquals(args[call][2], 'rpm')
                self.assertEquals(args[call][3], unit)
                self.assertEquals(args[call][4], cfg)
                self.assertEquals(args[call][5].__class__, ProfilerConduit)
                call += 1

    def test_profiler_no_exception(self):
        # Setup
        self.populate()
        profiler, cfg = plugins.get_profiler_by_type('rpm')
        profiler.units_applicable = Mock(side_effect=KeyError)
        # Test
        units = {'rpm': [{'name':'zsh'},
                         {'name':'ksh'}],
                 'mock-type': [{'name':'abc'},
                               {'name':'def'}]
                }
        manager = factory.consumer_applicability_manager()
        result = manager.units_applicable(self.CONSUMER_CRITERIA, self.REPO_CRITERIA, units)
        self.assertTrue('test-1' in result.keys())
        self.assertTrue('test-2' in result.keys())

    def test_no_exception_for_profiler_notfound(self):
        # Setup
        self.populate()
        # Test
        units = {'rpm': [{'name':'zsh'}],
                 'xxx': [{'name':'abc'}]
                }
        manager = factory.consumer_applicability_manager()
        result = manager.units_applicable(self.CONSUMER_CRITERIA, self.REPO_CRITERIA, units)
        self.assertTrue('test-1' in result.keys())
        self.assertTrue('test-2' in result.keys())
