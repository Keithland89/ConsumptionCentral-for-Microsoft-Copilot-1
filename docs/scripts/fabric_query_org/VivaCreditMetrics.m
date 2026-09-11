let
    Tbl = GetTable("viva_credits_weekly"),
    Empty = #table(type table [
        PersonId = text, UserPrincipalName = text, PeopleHistoricalId = text, EntraId = text,
        ServiceId = text, ServiceName = text, SpendingPolicyId = text, MetricDate = date,
        SessionCount = Int64.Type, SpendingPolicyLimit = Int64.Type, CreditsUsed = number,
        UserLimit = Int64.Type, PolicyName = text, IncludedServices = text
    ], {}),
    Key = (n as text) as text => Text.Lower(Text.Remove(n, {" ", "_", "-"})),
    Find = (cols as list, aliases as list) as nullable text =>
        List.First(List.Select(cols, each List.Contains(aliases, Key(_))), null),
    Identity = (v as any) as nullable text =>
        if v = null then null else let t = Text.Lower(Text.Trim(Text.From(v))) in if t = "" then null else t,
    Result =
        if Tbl = null then Empty
        else
            let
                Cols = Table.ColumnNames(Tbl),
                UpnCol = Find(Cols, {"userprincipalname", "upn", "userprincipal", "email", "mail"}),
                PidCol = Find(Cols, {"personid", "personidnormalized", "personidnormalised"}),
                PhidCol = Find(Cols, {"peoplehistoricalid", "personhistoricalid", "phid"}),
                EntraCol = Find(Cols, {"entraid", "entraobjectid", "objectid", "aadobjectid", "aadid", "aad"}),
                WithUpn = if UpnCol = null then Table.AddColumn(Tbl, "UserPrincipalName", each null, type text)
                    else if UpnCol = "UserPrincipalName" then Tbl
                    else Table.RenameColumns(Tbl, {{UpnCol, "UserPrincipalName"}}),
                WithPid = if PidCol = null then Table.AddColumn(WithUpn, "PersonId",
                        each Identity(Record.Field(_, "UserPrincipalName")), type text)
                    else if PidCol = "PersonId" then WithUpn
                    else Table.RenameColumns(WithUpn, {{PidCol, "PersonId"}}),
                WithPhid = if PhidCol = null then Table.AddColumn(WithPid, "PeopleHistoricalId", each null, type text)
                    else if PhidCol = "PeopleHistoricalId" then WithPid
                    else Table.RenameColumns(WithPid, {{PhidCol, "PeopleHistoricalId"}}),
                WithEntra = if EntraCol = null then Table.AddColumn(WithPhid, "EntraId", each null, type text)
                    else if EntraCol = "EntraId" then WithPhid
                    else Table.RenameColumns(WithPhid, {{EntraCol, "EntraId"}}),
                Cleaned = Table.TransformColumns(WithEntra, {
                    {"PersonId", Identity, type nullable text},
                    {"UserPrincipalName", Identity, type nullable text},
                    {"PeopleHistoricalId", Identity, type nullable text},
                    {"EntraId", Identity, type nullable text}
                }),
                WithResolvedPid = Table.AddColumn(Cleaned, "__ResolvedPersonId",
                    each if [PersonId] <> null and [PersonId] <> "" then [PersonId] else [UserPrincipalName],
                    type nullable text),
                Normalised = Table.RenameColumns(
                    Table.RemoveColumns(WithResolvedPid, {"PersonId"}), {{"__ResolvedPersonId", "PersonId"}}),
                Renamed = Table.RenameColumns(Normalised, {
                    {"session_count","SessionCount"}, {"spending_policy_limit","SpendingPolicyLimit"},
                    {"credits_used","CreditsUsed"}, {"user_limit","UserLimit"},
                    {"service_id","ServiceId"}, {"service_name","ServiceName"},
                    {"spending_policy_id","SpendingPolicyId"}, {"metric_date","MetricDate"},
                    {"policy_name","PolicyName"}, {"included_services","IncludedServices"}
                }, MissingField.Ignore),
                Kept = Table.SelectColumns(Renamed, List.Union({
                    {
                        "PersonId","UserPrincipalName","PeopleHistoricalId","EntraId",
                        "ServiceId","ServiceName","SpendingPolicyId","MetricDate",
                        "SessionCount","SpendingPolicyLimit","CreditsUsed","UserLimit",
                        "PolicyName","IncludedServices"
                    },
                    Table.ColumnNames(Renamed)
                }), MissingField.UseNull),
                Typed = Table.TransformColumnTypes(Kept, {
                    {"PersonId", type text}, {"UserPrincipalName", type text},
                    {"PeopleHistoricalId", type text}, {"EntraId", type text},
                    {"ServiceId", type text}, {"ServiceName", type text},
                    {"SpendingPolicyId", type text}, {"MetricDate", type date},
                    {"SessionCount", Int64.Type}, {"SpendingPolicyLimit", Int64.Type},
                    {"CreditsUsed", type number}, {"UserLimit", Int64.Type},
                    {"PolicyName", type text}, {"IncludedServices", type text}
                })
            in
                Typed
in
    Result
