"""
Static price table used to estimate monthly compute cost.
"""

import logging

import yaml

logger = logging.getLogger('pricing')

DEFAULT_HOURS_PER_MONTH = 730
DEFAULT_CURRENCY = 'USD'


class PriceTable(object):
    """Hourly list prices per provider and instance size."""

    def __init__(self, prices, hours_per_month=DEFAULT_HOURS_PER_MONTH,
                 currency=DEFAULT_CURRENCY):
        self.prices = dict((p, dict(sizes or {})) for p, sizes in prices.items())
        self.hours_per_month = hours_per_month
        self.currency = currency

    @classmethod
    def from_file(cls, path):
        """Load a table from a YAML file with hours_per_month, currency and
        one mapping of size -> hourly price per provider."""
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
        hours = data.pop('hours_per_month', DEFAULT_HOURS_PER_MONTH)
        currency = data.pop('currency', DEFAULT_CURRENCY)
        return cls(data, hours_per_month=hours, currency=currency)

    def hourly(self, provider, size):
        """Hourly price of one instance; 0.0 (with a warning) if unknown."""
        sizes = self.prices.get(provider)
        if sizes is None:
            logger.warning('No prices for provider %s', provider)
            return 0.0
        if size not in sizes:
            logger.warning('No %s price for size %s, counting it as 0.0', provider, size)
            return 0.0
        return float(sizes[size])

    def monthly(self, provider, sizes):
        """Monthly cost of one running instance per entry in ``sizes``."""
        hourly_total = 0.0
        for size in sizes:
            hourly_total += self.hourly(provider, size)
        return round(hourly_total * self.hours_per_month, 2)
