"""
Synthetic XBRL instance generator for test fixtures.
Generates valid XML strings conforming to IDX taxonomy structures without real BEI filings.
"""

from __future__ import annotations


def generate_mock_xbrl(
    ticker: str = "TEST",
    instant_date: str = "2023-12-31",
    start_date: str = "2023-01-01",
    end_date: str = "2023-12-31",
    assets: int = 100_000_000_000,
    current_assets: int = 40_000_000_000,
    non_current_assets: int = 60_000_000_000,
    liabilities: int = 70_000_000_000,
    current_liabilities: int = 30_000_000_000,
    non_current_liabilities: int = 40_000_000_000,
    equity: int = 30_000_000_000,
    cash_bs: int = 5_000_000_000,
    cash_cf: int = 5_000_000_000,
    revenue: int = 80_000_000_000,
    profit_loss: int = 2_000_000_000,
    cfo: int = -1_500_000_000,
    include_dimensional_contexts: bool = True,
    dimensional_revenue: int = 15_000_000_000,
) -> str:
    """Generate a synthetic XBRL XML string for testing."""
    dim_context_xml = ""
    dim_facts_xml = ""

    if include_dimensional_contexts:
        dim_context_xml = f"""
    <xbrli:context id="C_Segment_Precast">
        <xbrli:entity>
            <xbrli:identifier scheme="http://www.idx.co.id/ticker">{ticker}</xbrli:identifier>
            <xbrli:segment>
                <xbrldi:explicitMember dimension="idx-cor:SegmentAxis">
                    idx-cor:PrecastMember
                </xbrldi:explicitMember>
            </xbrli:segment>
        </xbrli:entity>
        <xbrli:period>
            <xbrli:startDate>{start_date}</xbrli:startDate>
            <xbrli:endDate>{end_date}</xbrli:endDate>
        </xbrli:period>
    </xbrli:context>
    <xbrli:context id="C_Scenario_Restatement">
        <xbrli:entity>
            <xbrli:identifier scheme="http://www.idx.co.id/ticker">{ticker}</xbrli:identifier>
        </xbrli:entity>
        <xbrli:period>
            <xbrli:instant>{instant_date}</xbrli:instant>
        </xbrli:period>
        <xbrli:scenario>
            <xbrldi:typedMember dimension="idx-cor:RestatementAxis">
                <idx-cor:RestatementValue>Original</idx-cor:RestatementValue>
            </xbrldi:typedMember>
        </xbrli:scenario>
    </xbrli:context>
    """
        dim_facts_xml = f"""
    <idx-cor:Revenues contextRef="C_Segment_Precast" unitRef="IDR" decimals="0">
        {dimensional_revenue}
    </idx-cor:Revenues>
    <idx-cor:Assets contextRef="C_Scenario_Restatement" unitRef="IDR" decimals="0">
        999999999999
    </idx-cor:Assets>
    """

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<xbrli:xbrl
    xmlns:xbrli="http://www.xbrl.org/2003/instance"
    xmlns:idx-cor="http://www.idx.co.id/xbrl/taxonomy/idx-cor"
    xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
    xmlns:iso4217="http://www.xbrl.org/2003/iso4217">

    <xbrli:unit id="IDR">
        <xbrli:measure>iso4217:IDR</xbrli:measure>
    </xbrli:unit>

    <xbrli:context id="C_Current_Instant">
        <xbrli:entity>
            <xbrli:identifier scheme="http://www.idx.co.id/ticker">{ticker}</xbrli:identifier>
        </xbrli:entity>
        <xbrli:period>
            <xbrli:instant>{instant_date}</xbrli:instant>
        </xbrli:period>
    </xbrli:context>

    <xbrli:context id="C_Current_Duration">
        <xbrli:entity>
            <xbrli:identifier scheme="http://www.idx.co.id/ticker">{ticker}</xbrli:identifier>
        </xbrli:entity>
        <xbrli:period>
            <xbrli:startDate>{start_date}</xbrli:startDate>
            <xbrli:endDate>{end_date}</xbrli:endDate>
        </xbrli:period>
    </xbrli:context>
{dim_context_xml}
    <!-- Balance Sheet Facts -->
    <idx-cor:Assets contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        {assets}
    </idx-cor:Assets>
    <idx-cor:CurrentAssets contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        {current_assets}
    </idx-cor:CurrentAssets>
    <idx-cor:NonCurrentAssets contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        {non_current_assets}
    </idx-cor:NonCurrentAssets>
    <idx-cor:Liabilities contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        {liabilities}
    </idx-cor:Liabilities>
    <idx-cor:CurrentLiabilities contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        {current_liabilities}
    </idx-cor:CurrentLiabilities>
    <idx-cor:NonCurrentLiabilities contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        {non_current_liabilities}
    </idx-cor:NonCurrentLiabilities>
    <idx-cor:Equity contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        {equity}
    </idx-cor:Equity>
    <idx-cor:CashAndCashEquivalents contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        {cash_bs}
    </idx-cor:CashAndCashEquivalents>

    <!-- Key Pos Items -->
    <idx-cor:TradeReceivablesThirdParties
        contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        8000000000
    </idx-cor:TradeReceivablesThirdParties>
    <idx-cor:TradeReceivablesRelatedParties
        contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        2000000000
    </idx-cor:TradeReceivablesRelatedParties>
    <idx-cor:ContractAssetsCurrent contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        12000000000
    </idx-cor:ContractAssetsCurrent>
    <idx-cor:ContractAssetsNonCurrent contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        3000000000
    </idx-cor:ContractAssetsNonCurrent>
    <idx-cor:ContractLiabilitiesCurrent contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        5000000000
    </idx-cor:ContractLiabilitiesCurrent>
    <idx-cor:ShortTermBankLoans contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        6000000000
    </idx-cor:ShortTermBankLoans>
    <idx-cor:CurrentMaturitiesOfLongTermBankLoans
        contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        4000000000
    </idx-cor:CurrentMaturitiesOfLongTermBankLoans>
    <idx-cor:CurrentMaturitiesOfBondsPayable
        contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        2000000000
    </idx-cor:CurrentMaturitiesOfBondsPayable>
    <idx-cor:CurrentPortionOfLeaseLiabilities
        contextRef="C_Current_Instant" unitRef="IDR" decimals="0">
        500000000
    </idx-cor:CurrentPortionOfLeaseLiabilities>

    <!-- Income Statement & Cash Flow Facts -->
    <idx-cor:Revenues contextRef="C_Current_Duration" unitRef="IDR" decimals="0">
        {revenue}
    </idx-cor:Revenues>
    <idx-cor:ProfitLoss contextRef="C_Current_Duration" unitRef="IDR" decimals="0">
        {profit_loss}
    </idx-cor:ProfitLoss>
    <idx-cor:NetCashFlowsFromUsedInOperatingActivities
        contextRef="C_Current_Duration" unitRef="IDR" decimals="0">
        {cfo}
    </idx-cor:NetCashFlowsFromUsedInOperatingActivities>
    <idx-cor:CashAndCashEquivalentsCashFlowStatement
        contextRef="C_Current_Duration" unitRef="IDR" decimals="0">
        {cash_cf}
    </idx-cor:CashAndCashEquivalentsCashFlowStatement>
{dim_facts_xml}
</xbrli:xbrl>
"""
    return xml.strip()
