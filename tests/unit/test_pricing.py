import logging
import os

import pytest

from pricing import PriceTable

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRICING_FILE = os.path.join(REPO_ROOT, 'config', 'pricing.yaml')


@pytest.fixture
def table():
    return PriceTable.from_file(PRICING_FILE)


def test_loads_repo_config_file(table):
    assert table.hours_per_month == 730
    assert table.currency == 'USD'
    assert table.hourly('azure', 'Standard_B2s') == 0.0416


def test_hourly_known_size(table):
    assert table.hourly('aws', 't2.micro') == 0.0116


def test_monthly_sums_sizes_over_hours_per_month(table):
    assert table.monthly('aws', ['t2.micro', 'm4.large']) == round((0.0116 + 0.10) * 730, 2)


def test_monthly_counts_repeated_sizes(table):
    assert table.monthly('aws', ['t2.micro', 't2.micro']) == round(2 * 0.0116 * 730, 2)


def test_monthly_of_no_instances_is_zero(table):
    assert table.monthly('azure', []) == 0.0


def test_unknown_size_is_zero_with_warning(table, caplog):
    with caplog.at_level(logging.WARNING):
        assert table.hourly('aws', 'x9.huge') == 0.0
    assert any('x9.huge' in r.getMessage() and r.levelno == logging.WARNING
               for r in caplog.records)


def test_unknown_size_contributes_nothing_to_monthly(table, caplog):
    with caplog.at_level(logging.WARNING):
        assert table.monthly('aws', ['t2.micro', 'x9.huge']) == round(0.0116 * 730, 2)


def test_unknown_provider_is_zero(table):
    assert table.hourly('gcp', 'n1-standard-1') == 0.0
    assert table.monthly('gcp', ['n1-standard-1']) == 0.0


def test_custom_hours_per_month(tmpdir):
    path = tmpdir.join('p.yaml')
    path.write('hours_per_month: 100\ncurrency: EUR\naws: {t2.micro: 0.5}\n')
    custom = PriceTable.from_file(str(path))
    assert custom.currency == 'EUR'
    assert custom.monthly('aws', ['t2.micro']) == 50.0
