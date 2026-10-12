from __future__ import annotations

from datetime import date

from nselib.mutual_funds import (
    amfi_monthly_data as _amfi_monthly_data,
    amfi_monthly_historical_data as _amfi_monthly_historical_data,
    amfi_monthly_report_links as _amfi_monthly_report_links,
)
from nselib.nsdl_fpi import (
    fetch_nsdl_fpi_derivative_activity,
    fetch_nsdl_fpi_investment_activity,
    fetch_nsdl_fpi_latest_derivative_activity,
    fetch_nsdl_fpi_latest_investment_activity,
)


def nsdl_fpi_investment_activity(trade_date: str):
    """
    NSDL FPI investment activity for the traded date provided.
    :param trade_date: eg:'30-10-2025'
    :return: pandas dataframe
    """
    return fetch_nsdl_fpi_investment_activity(trade_date)


def nsdl_fpi_latest_investment_activity():
    """
    Latest NSDL FPI investment activity.
    :return: pandas dataframe
    """
    return fetch_nsdl_fpi_latest_investment_activity()


def nsdl_fpi_derivative_activity(trade_date: str):
    """
    NSDL FPI derivative activity for the traded date provided.
    :param trade_date: eg:'30-10-2025'
    :return: pandas dataframe
    """
    return fetch_nsdl_fpi_derivative_activity(trade_date)


def nsdl_fpi_latest_derivative_activity():
    """
    Latest NSDL FPI derivative activity.
    :return: pandas dataframe
    """
    return fetch_nsdl_fpi_latest_derivative_activity()


def amfi_monthly_report_links():
    """
    List all report links exposed on the AMFI monthly archive page.
    """
    return _amfi_monthly_report_links()


def amfi_monthly_data(
    report_month: str | date,
    file_type_priority: tuple[str, ...] | list[str] | None = None,
):
    """
    Fetch a single month AMFI report and return normalized row-wise records.
    """
    return _amfi_monthly_data(
        report_month=report_month,
        file_type_priority=file_type_priority,
    )


def amfi_monthly_historical_data(
    from_month: str | date | None = None,
    to_month: str | date | None = None,
    file_type_priority: tuple[str, ...] | list[str] | None = None,
    include_all_file_variants: bool = False,
    strict: bool = False,
):
    """
    Fetch AMFI monthly reports for a historical month range.
    """
    return _amfi_monthly_historical_data(
        from_month=from_month,
        to_month=to_month,
        file_type_priority=file_type_priority,
        include_all_file_variants=include_all_file_variants,
        strict=strict,
    )
