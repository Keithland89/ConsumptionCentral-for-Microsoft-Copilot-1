let
    Metrics = Table.SelectColumns(VivaCreditMetrics, {
        "PersonId","UserPrincipalName","MetricDate","ServiceName",
        "SpendingPolicyId","CreditsUsed","SessionCount"
    }),
    Joined = Table.NestedJoin(Metrics, {"PersonId"}, VivaSeatRoster, {"PersonId"}, "seat", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Joined, "seat", {"userPrincipalName"}, {"SeatUpn"}),
    // The roster's first real UPN (else PersonId) is the relationship key for every week.
    Coalesced = Table.AddColumn(Expanded, "ResolvedUpn",
        each Text.Lower(Text.Trim(Text.From(
            if [SeatUpn] <> null and [SeatUpn] <> "" then [SeatUpn]
            else if [UserPrincipalName] <> null and [UserPrincipalName] <> "" then [UserPrincipalName]
            else [PersonId]))), type text),
    Dropped = Table.RemoveColumns(Coalesced, {"UserPrincipalName","SeatUpn"}),
    Named = Table.RenameColumns(Dropped, {{"ResolvedUpn","UserPrincipalName"}}),
    Selected = Table.SelectColumns(Named, {
        "PersonId","UserPrincipalName","MetricDate","ServiceName",
        "SpendingPolicyId","CreditsUsed","SessionCount"
    }),
    Typed = Table.TransformColumnTypes(Selected, {
        {"PersonId", type text},{"UserPrincipalName", type text},
        {"MetricDate", type datetime},{"ServiceName", type text},
        {"SpendingPolicyId", type text},{"CreditsUsed", type number},
        {"SessionCount", Int64.Type}
    })
in
    Typed
