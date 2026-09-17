let
    // Prefer the ValueLens-aligned table so a single org ingestion feeds both templates,
    // then fall back to the original Consumption Central name for existing deployments.
    OrgTableNames = {"copilot_org_data", "org_attributes"},
    Tbl = List.First(
        List.Select(
            List.RemoveNulls(List.Transform(OrgTableNames, GetTable)),
            each not Table.IsEmpty(_)),
        null),
    Key = (n as text) as text => Text.Lower(Text.Remove(n, {" ", "_", "-"})),
    Ident = (v as any) as nullable text =>
        if v = null then null else let t = Text.Lower(Text.Trim(Text.From(v))) in if t = "" then null else t,
    IdAliases = {
        "personid", "personidnormalized", "personidnormalised",
        "userprincipalname", "upn", "userprincipal", "email", "mail",
        "entraid", "entraobjectid", "objectid", "aadobjectid", "aadid",
        "peoplehistoricalid", "personhistoricalid", "phid"
    },
    // copilot_org_data is a full directory (tens of thousands of rows), while org_attributes
    // was already scoped. Without this filter the directory sets the grain of Org and every
    // per-user count reports the whole company instead of the licensed population.
    RosterKeys = List.Buffer(List.Distinct(List.RemoveNulls(
        List.Transform(VivaSeatRoster[PersonId], Ident)
        & List.Transform(VivaSeatRoster[userPrincipalName], Ident)))),
    // Record lookup gives an O(1) membership test; List.Contains would rescan per row.
    RosterSet = Record.FromList(List.Repeat({true}, List.Count(RosterKeys)), RosterKeys),
    InRoster = (v as any) as logical =>
        let k = Ident(v) in if k = null then false else Record.FieldOrDefault(RosterSet, k, false),
    Result =
        if Tbl = null or Table.IsEmpty(Tbl) then null
        else
            let
                Typed = Table.TransformColumnTypes(Tbl,
                    List.Transform(Table.ColumnNames(Tbl), each {_, type text})),
                Trimmed = Table.TransformColumns(Typed,
                    List.Transform(Table.ColumnNames(Typed), each
                        {_, (v) => if v = null then null else Text.Trim(Text.From(v)), type nullable text})),
                IdCols = List.Select(Table.ColumnNames(Trimmed), each List.Contains(IdAliases, Key(_))),
                Scoped =
                    if List.IsEmpty(RosterKeys) or List.IsEmpty(IdCols) then Trimmed
                    else Table.SelectRows(Trimmed,
                        (row) => List.AnyTrue(List.Transform(IdCols, each InRoster(Record.Field(row, _))))),
                Final = if Table.IsEmpty(Scoped) then Trimmed else Scoped
            in
                Final
in
    Result