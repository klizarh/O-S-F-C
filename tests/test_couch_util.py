"""Tests for the CouchUtil record-building functions.

These tests exercise the pure-logic helpers that build JSON structures
from observation lists.  They do NOT require a running CouchDB instance.
"""

from CouchUtil import (
    buildCore,
    processEnv,
    processState,
    processAgro,
    processPheno,
    TS, FIELD, ACTIVITY, TRIAL, PLOT, SUBJECT, ATTRIBUTE, VALUE,
    UNITS, PARTICIPANT, STATUS, COMMENT,
)


def _make_row(activity, trial='', plot='Left_Side', subject='Air',
              attribute='Temperature', value=27.5, units='Celsius',
              participant='SI7021', status='Success', comment=''):
    """Helper to build a full 12-element row for testing."""
    return [
        '2024-01-01T12:00:00',  # TS
        'field-uuid-1234',       # FIELD
        activity,                # ACTIVITY
        trial,                   # TRIAL
        plot,                    # PLOT
        subject,                 # SUBJECT
        attribute,               # ATTRIBUTE
        value,                   # VALUE
        units,                   # UNITS
        participant,             # PARTICIPANT
        status,                  # STATUS
        comment,                 # COMMENT
    ]


class TestBuildCore:
    def test_device_participant(self):
        row = _make_row('Environment_Observation')
        rec = buildCore(row)
        assert rec['participant'] == {'type': 'device', 'name': 'SI7021'}

    def test_person_participant(self):
        row = _make_row('Environment_Observation', participant=['person', 'hmw'])
        rec = buildCore(row)
        assert rec['participant'] == {'type': 'person', 'name': 'hmw'}

    def test_timestamp_present(self):
        row = _make_row('Environment_Observation')
        rec = buildCore(row)
        assert rec['start_date'] == {'timestamp': '2024-01-01T12:00:00'}

    def test_status_without_comment(self):
        row = _make_row('Environment_Observation', comment='')
        rec = buildCore(row)
        assert rec['status'] == {
            'status': 'Complete',
            'status_qualifier': 'Success',
        }

    def test_status_with_comment(self):
        row = _make_row('Environment_Observation', comment='test note')
        rec = buildCore(row)
        assert rec['status']['comment'] == 'test note'


class TestProcessEnv:
    def test_activity_type(self):
        row = _make_row('Environment_Observation')
        rec = processEnv(row)
        assert rec['activity_type'] == 'Environment_Observation'

    def test_subject_structure(self):
        row = _make_row('Environment_Observation')
        rec = processEnv(row)
        assert rec['subject']['name'] == 'Air'
        assert rec['subject']['attribute']['name'] == 'Temperature'
        assert rec['subject']['attribute']['value'] == 27.5
        assert rec['subject']['attribute']['units'] == 'Celsius'
        assert rec['subject']['location'] == 'Left_Side'

    def test_location_field(self):
        row = _make_row('Environment_Observation')
        rec = processEnv(row)
        assert rec['location'] == {'field': 'field-uuid-1234'}


class TestProcessState:
    def test_activity_type(self):
        row = _make_row('State_Change', subject='Lights', attribute='State',
                        value='ON', units='state', participant='Light')
        rec = processState(row)
        assert rec['activity_type'] == 'State_Change'

    def test_participant_is_device(self):
        row = _make_row('State_Change', participant='Light')
        rec = processState(row)
        assert rec['participant'] == {'type': 'device', 'name': 'Light'}


class TestProcessAgro:
    def test_activity_type(self):
        row = _make_row('Agronomic_Activity', trial='trial-uuid',
                        plot='Planted', subject='', attribute='',
                        value='', units='', participant=['person', 'hmw'])
        rec = processAgro(row)
        assert rec['activity_type'] == 'Agronomic_Activity'

    def test_no_subject_when_empty(self):
        row = _make_row('Agronomic_Activity', trial='trial-uuid',
                        plot='Planted', subject='', attribute='',
                        value='', units='', participant=['person', 'hmw'])
        rec = processAgro(row)
        assert 'subject' not in rec

    def test_subject_when_present(self):
        row = _make_row('Agronomic_Activity', trial='trial-uuid',
                        plot='Watered', subject='Plant', attribute='Water',
                        value=100, units='ml', participant=['person', 'hmw'])
        rec = processAgro(row)
        assert rec['subject']['name'] == 'Plant'

    def test_location_has_trial(self):
        row = _make_row('Agronomic_Activity', trial='trial-uuid',
                        plot='Planted', subject='', attribute='',
                        value='', units='', participant=['person', 'hmw'])
        rec = processAgro(row)
        assert rec['location']['trial'] == 'trial-uuid'


class TestProcessPheno:
    def test_activity_type(self):
        row = _make_row('Phenotype_Observation', trial='trial-uuid',
                        plot=1, subject='Plant', attribute='Weight',
                        value=125, units='g', participant=['person', 'hmw'])
        rec = processPheno(row)
        assert rec['activity_type'] == 'Phenotype_Observation'

    def test_location_has_plot(self):
        row = _make_row('Phenotype_Observation', trial='trial-uuid',
                        plot=1, subject='Plant', attribute='Weight',
                        value=125, units='g', participant=['person', 'hmw'])
        rec = processPheno(row)
        assert rec['location']['plot'] == 1
        assert rec['location']['trial'] == 'trial-uuid'
