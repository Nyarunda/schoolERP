# Growth and health KPIs: acceptance

| # | Given / when | Then | Test | On admin site |
|---|---|---|---|---|
| 1 | A new paying school (4,000/month, paid 3,000) | Paying +1, MRR +4,000, ARR = MRR×12, this month's MRR trend and collections move, new schools +1 | `test_growth::test_kpis_move_with_a_new_paying_school` | [ ] |
| 2 | Its 1,000 balance, then 45 days overdue | Owed +1,000; in 31–60 days | `::test_ageing_and_owed` | [ ] |
| 3 | County Kisii; plan; subscription cancelled | County and plan listed; lost +1, churn > 0 | `::test_counties_plans_and_churn` | [ ] |
| 4 | An expense of 1,500 | Costs this month +1,500; net = collected − commission − costs | `::test_costs_count_in_cash_vs_costs` | [ ] |
| 5 | Non-admin | Refused | `::test_admin_only` | [ ] |

## Docs
- [x] README, CHANGELOG
