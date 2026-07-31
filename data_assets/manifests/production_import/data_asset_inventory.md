## Data Asset Inventory

Root: `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets`
Existing assets: 5 / 14
Required ready: yes
Stock master ready: yes

| Asset | Scope | Required | Exists | Rows | Date Range | Missing Columns | Path |
|---|---|---:|---:|---:|---|---|---|
| historical_stock_master | production | yes | yes | 4924 | n/a to n/a | none | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/stock_master/historical_stock_master.csv` |
| daily_quotes | production | yes | yes | 3894242 | 2023-01-03 to 2026-07-24 | none | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/market/daily_quotes.csv` |
| fundamental_factors | production_optional | no | yes | 99628 | 2020-04-08 to 2026-07-24 | none | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/fundamentals/fundamental_factors.csv` |
| dividend_events | production_optional | no | yes | 20288 | n/a to n/a | none | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/fundamentals/dividend_events.csv` |
| daily_fund_flows | production_optional | no | no | 0 | n/a to n/a | date, symbol, mainNetInflow, netInflowLarge, netInflowXlarge | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/market/daily_fund_flows.csv` |
| margin_trades | production_optional | no | yes | 2399572 | 2023-01-03 to 2026-07-24 | none | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/market/margin_trades.csv` |
| dragon_tiger_details | production_optional | no | no | 0 | n/a to n/a | date, symbol, abnormalType | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/events/dragon_tiger_details.csv` |
| announcements | production_optional | no | no | 0 | n/a to n/a | date, symbol, title | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/events/announcements.csv` |
| index_constituents | production_optional | no | no | 0 | n/a to n/a | date, indexCode, symbol, weight | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/index/index_constituents.csv` |
| industry_classification | production_optional | no | no | 0 | n/a to n/a | date, symbol, industryLV1Name, industryName | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/industry/industry_classification.csv` |
| investoday_candidate_stock_master | candidate | no | no | 0 | n/a to n/a | symbol, stockCode, exchangeCode, stockName, stockType, listDate, delistDate, listStatus | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/investoday_candidate/stock_master.csv` |
| investoday_candidate_daily_quotes | candidate | no | no | 0 | n/a to n/a | date, symbol, open, high, low, close, volume, amount | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/investoday_candidate/daily_quotes.csv` |
| investoday_candidate_universe | candidate | no | no | 0 | n/a to n/a | symbol, stockCode, stockName | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/investoday_candidate/realtime_universe.csv` |
| investoday_candidate_industry | candidate | no | no | 0 | n/a to n/a | date, symbol, industryLV1Name, industryName | `/Users/wushuaiwei/Documents/skill hub/a_share_quant_agent_mvp/data_assets/investoday_candidate/industry_classification.csv` |

### Stock Master Validation

Status: `production_ready`
Coverage level: `full_historical_stock_master`
Hard failed: 0
