from __future__ import annotations

from .aws_base import AwsBase
from .aws_compute import AwsComputeMixin
from .aws_ssm import AwsSsmMixin


class AwsCli(AwsSsmMixin, AwsComputeMixin, AwsBase):
    """AWS CLI adapter with explicit profile/region and sanitized errors."""
