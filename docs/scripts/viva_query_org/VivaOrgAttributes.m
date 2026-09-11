let
    Source = try VivaOrgSource otherwise null,
    Key = (n as text) as text => Text.Lower(Text.Remove(n, {" ", "_", "-"})),
    Identity = (v as any) as nullable text =>
        if v = null then null
        else let t = Text.Lower(Text.Trim(Text.From(v))) in if t = "" then null else t,
    Result =
        if Source = null then null
        else
            let
                Cols = Table.ColumnNames(Source),
                PhidCols = List.Select(Cols, each List.Contains(
                    {"peoplehistoricalid", "personhistoricalid", "phid"}, Key(_))),
                MetricIds = Table.SelectColumns(VivaCreditMetrics, {"PersonId", "PeopleHistoricalId"}),
                JoinedRoster = Table.NestedJoin(MetricIds, {"PersonId"}, VivaSeatRoster, {"PersonId"},
                    "roster", JoinKind.Inner),
                ExpandedRoster = Table.ExpandTableColumn(JoinedRoster, "roster",
                    {"userPrincipalName"}, {"UserPrincipalName"}),
                NormalIds = Table.TransformColumns(ExpandedRoster, {
                    {"PersonId", Identity, type nullable text},
                    {"PeopleHistoricalId", Identity, type nullable text},
                    {"UserPrincipalName", Identity, type nullable text}
                }),
                ResolvedIds = Table.AddColumn(NormalIds, "ResolvedKey",
                    each if [UserPrincipalName] <> null then [UserPrincipalName] else [PersonId],
                    type nullable text),
                Real = Table.SelectRows(ResolvedIds,
                    each [PeopleHistoricalId] <> null and [ResolvedKey] <> null),
                // Buffer both grouped rows and nested key lists before building the PHID map.
                Grouped = Table.Buffer(Table.Group(Real, {"PeopleHistoricalId"}, {
                    {"Keys", each List.Buffer(List.Distinct([ResolvedKey])), type list}
                })),
                // Conflicting PHIDs are not evidence for choosing an arbitrary person.
                Unique = Table.Buffer(Table.SelectRows(Grouped, each List.Count([Keys]) = 1)),
                Map = Record.FromList(List.Buffer(List.Transform(Unique[Keys], each _{0})),
                    List.Buffer(Unique[PeopleHistoricalId])),
                Records = List.Buffer(List.Transform(Table.ToRecords(Source), (row) =>
                    let
                        Phids = List.Distinct(List.RemoveNulls(
                            List.Transform(PhidCols, each Identity(Record.Field(row, _))))),
                        Phid = if List.Count(Phids) = 1 then Phids{0} else null,
                        Resolved = if Phid = null then null else Record.FieldOrDefault(Map, Phid, null)
                    in
                        Record.Combine({row, [UserPrincipalName = Resolved]}))),
                Named = Table.FromRecords(Records, List.Union({Cols, {"UserPrincipalName"}}),
                    MissingField.UseNull),
                Final = Table.SelectRows(Named, each [UserPrincipalName] <> null)
            in
                if List.IsEmpty(PhidCols) or Table.IsEmpty(Final) then null else Final
in
    // Only this optional named-table fallback is guarded; consumption identity errors are not.
    try Result otherwise null
