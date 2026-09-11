let
    Source = VivaCreditMetrics,
    Key = (n as text) as text => Text.Lower(Text.Remove(n, {" ", "_", "-"})),
    NotOrg = {
        "userprincipalname", "upn", "userprincipal", "email", "mail",
        "entraid", "entraobjectid", "objectid", "aadobjectid", "aadid", "aad",
        "personid", "personidnormalized", "personidnormalised",
        "peoplehistoricalid", "personhistoricalid", "phid",
        "serviceid", "servicename", "spendingpolicyid", "spendingpolicyname",
        "policyname", "policylimit", "policyservicesincluded", "includedservices",
        "metricdate", "date", "week", "weekstart", "sessioncount",
        "spendingpolicylimit", "totalcopilotcreditsused", "creditsused", "userlimit", "planlimit",
        "iscopilotlicensed", "standardtimezone", "timezone"
    },
    OrgCols = List.Select(Table.ColumnNames(Source), each not List.Contains(NotOrg, Key(_))),
    Clean = (v as any) as nullable text =>
        if v = null then null else let t = Text.Trim(Text.From(v)) in if t = "" then null else t,
    Result =
        if List.IsEmpty(OrgCols) then null
        else
            let
                Picked = Table.SelectColumns(Source, {"PersonId"} & OrgCols),
                AsText = Table.TransformColumns(Picked,
                    List.Transform(OrgCols, each {_, Clean, type nullable text})),
                // Group before joining: roster resolves all weeks of a person to one key.
                Grouped = Table.Buffer(Table.Group(AsText, {"PersonId"}, List.Transform(OrgCols, (c) =>
                    {c, each List.First(List.RemoveNulls(Table.Column(_, c)), null), type nullable text}))),
                // Resolve before expanding custom columns so helper names cannot collide.
                RosterKeys = Table.Buffer(Table.AddColumn(
                    Table.SelectColumns(VivaSeatRoster, {"PersonId", "userPrincipalName"}),
                    "UserPrincipalName", each
                        let Upn = Clean([userPrincipalName])
                        in Text.Lower(if Upn = null then Text.Trim(Text.From([PersonId])) else Upn),
                    type nullable text)),
                Joined = Table.NestedJoin(RosterKeys, {"PersonId"}, Grouped, {"PersonId"},
                    "__attributes", JoinKind.LeftOuter),
                NormalKeys = Table.Buffer(Table.ExpandTableColumn(
                    Table.SelectColumns(Joined, {"PersonId", "UserPrincipalName", "__attributes"}),
                    "__attributes", OrgCols)),
                Live = List.Select(OrgCols, (c) => List.NonNullCount(Table.Column(NormalKeys, c)) > 0)
            in
                if List.IsEmpty(Live) then null
                else Table.SelectColumns(NormalKeys, {"PersonId", "UserPrincipalName"} & Live)
in
    Result
