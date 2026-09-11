let
    Headers = VivaConnectorSource,
    Cols = Table.ColumnNames(Headers),
    Key = (n as text) as text => Text.Lower(Text.Remove(n, {" ", "_", "-"})),
    Identity = (v as any) as nullable text =>
        if v = null then null
        else let t = Text.Lower(Text.Trim(Text.From(v))) in if t = "" then null else t,
    IdentitySpecs = {
        {"UserPrincipalName", {"userprincipalname", "upn", "userprincipal", "email", "mail"}},
        {"PersonId", {"personid", "personidnormalized", "personidnormalised"}},
        {"EntraId", {"entraid", "entraobjectid", "objectid", "aadobjectid", "aadid", "aad"}},
        {"PeopleHistoricalId", {"peoplehistoricalid", "personhistoricalid", "phid"}}
    },
    IdentityColumns = List.Transform(IdentitySpecs, (spec) =>
        List.Combine(List.Transform(spec{1}, (alias) => List.Select(Cols, each Key(_) = alias)))),
    Value = (row as record, columns as list) as nullable text =>
        List.First(List.RemoveNulls(List.Transform(columns, each Identity(Record.Field(row, _)))), null),
    NonEmpty = Table.SelectRows(Headers, each
        List.AnyTrue(List.Transform(Record.FieldValues(_), (v) =>
            if v = null then false else if Value.Is(v, type text) then Text.Trim(v) <> "" else true))),
    // Retain every identity alias: org enrichment later needs the full crosswalk, not
    // only whichever canonical field happened to be selected first on a row.
    AllIdentityColumns = List.Distinct(List.Combine(IdentityColumns)),
    Normalised =
        if List.IsEmpty(AllIdentityColumns) then NonEmpty
        else Table.Buffer(Table.TransformColumns(NonEmpty,
            List.Transform(AllIdentityColumns, each {_, Identity, type nullable text}))),
    Ids = (row as record, columns as list) as list =>
        List.Distinct(List.RemoveNulls(List.Transform(columns, each Record.Field(row, _)))),
    KeysFor = (row as record) as list =>
        List.Combine(List.Transform(List.Positions(IdentityColumns), (kind) =>
            List.Transform(Ids(row, IdentityColumns{kind}), each Text.From(kind) & ":" & _))),
    IdentityRows =
        if List.IsEmpty(AllIdentityColumns) then #table(type table [], {})
        else Table.Distinct(Table.SelectColumns(Normalised, AllIdentityColumns)),
    IdentitySets = List.Buffer(List.Transform(Table.ToRecords(IdentityRows), (row) =>
        let
            Keys = List.Buffer(KeysFor(row)),
            Pids = List.Buffer(Ids(row, IdentityColumns{1})),
            Upns = List.Buffer(Ids(row, IdentityColumns{0})),
            Aads = List.Buffer(Ids(row, IdentityColumns{2})),
            Phids = List.Buffer(Ids(row, IdentityColumns{3}))
        in
            if List.IsEmpty(Keys) then error Error.Record(
                "VivaMissingIdentity",
                "A nonempty consumption row has no PersonId, UPN, EntraId or PeopleHistoricalId.",
                null)
            else [
                Keys = Keys,
                Pids = Pids,
                Upns = Upns,
                Aads = Aads,
                Phids = Phids
            ])),
    ToLinks = (rows as list) as table =>
        if List.IsEmpty(rows) then #table(type table [Alias = text, Label = text], {})
        else Table.FromRecords(rows, type table [Alias = text, Label = text]),
    Index = (links as table) as record =>
        let
            // Eager scalar index: Grouped is read once for labels and once for aliases.
            Grouped = Table.Buffer(Table.Group(links, {"Alias"}, {{"Label", each List.Min([Label]), type text}})),
            Labels = List.Buffer(Grouped[Label]),
            Aliases = List.Buffer(Grouped[Alias])
        in
            Record.FromList(Labels, Aliases),
    SeedIndex =
        if List.IsEmpty(IdentitySets) then []
        else Index(ToLinks(List.Combine(List.Transform(IdentitySets, (ids) =>
            let Label = List.Min(ids[Keys])
            in List.Transform(ids[Keys], (key) => [Alias = key, Label = Label]))))),
    AliasKeys = List.Buffer(Record.FieldNames(SeedIndex)),
    Advance = (labels as record) as record =>
        if List.IsEmpty(IdentitySets) then labels
        else
            Index(ToLinks(List.Combine(List.Transform(IdentitySets, (ids) =>
                let
                    Label = List.Min(List.Transform(ids[Keys], each Record.Field(labels, _)))
                in
                    List.Transform(ids[Keys], (key) => [Alias = key, Label = Label]))))),
    LabelStates = List.Generate(
        () => [Labels = SeedIndex, Changed = true],
        each [Changed],
        each
            let
                Previous = [Labels],
                Next = Advance(Previous)
            in [
                Labels = Next,
                Changed =
                    if List.IsEmpty(AliasKeys) then false
                    else List.AnyTrue(List.Transform(AliasKeys,
                        each Record.Field(Previous, _) <> Record.Field(Next, _)))
            ],
        each [Labels]),
    Labels = List.Last(LabelStates),
    ComponentRows =
        if List.IsEmpty(IdentitySets) then #table(
            type table [Component = text, Pids = list, Upns = list, Aads = list, Phids = list], {})
        else Table.FromRecords(List.Transform(IdentitySets, (ids) => [
            Component = Record.Field(Labels, ids[Keys]{0}),
            Pids = ids[Pids], Upns = ids[Upns], Aads = ids[Aads], Phids = ids[Phids]
        ]), type table [Component = text, Pids = list, Upns = list, Aads = list, Phids = list]),
    Components =
        if Table.IsEmpty(ComponentRows) then ComponentRows
        else Table.Buffer(Table.Group(ComponentRows, {"Component"},
            List.Transform({"Pids", "Upns", "Aads", "Phids"}, (column) =>
                {column, each List.Buffer(List.Sort(List.Distinct(List.Combine(Table.Column(_, column))),
                    Comparer.Ordinal)), type list}))),
    PidConflicts = Table.SelectRows(Components, each List.Count([Pids]) > 1),
    ResolvedComponents = Table.Buffer(Table.AddColumn(Components, "PersonId", each
        List.First(List.Combine({[Pids], [Upns], [Aads], [Phids]})), type text)),
    // Guard both the explicit person key and the roster relationship key (UPN, else PID).
    KeyOwners = Table.Buffer(Table.FromRecords(List.Combine(
        List.Transform(Table.ToRecords(ResolvedComponents), (person) =>
            List.Transform(List.Union({{person[PersonId]}, person[Upns]}),
                (key) => [Key = key, Component = person[Component]]))),
        type table [Key = text, Component = text])),
    KeyConflicts = Table.SelectRows(Table.Buffer(Table.Group(KeyOwners, {"Key"}, {
        {"Components", each List.Distinct([Component]), type list}
    })), each List.Count([Components]) > 1),
    ResolvedIndex =
        if not Table.IsEmpty(PidConflicts) then error Error.Record(
            "VivaIdentityConflict",
            "Connected consumption identities contain distinct explicit PersonIds.",
            [PersonIds = PidConflicts{0}[Pids]])
        else if not Table.IsEmpty(KeyConflicts) then error Error.Record(
            "VivaIdentityConflict",
            "Distinct consumption identities would share a PersonId or roster relationship key.",
            [Key = KeyConflicts{0}[Key]])
        else Record.FromList(ResolvedComponents[PersonId], ResolvedComponents[Component]),
    WithPid =
        if Record.FieldCount(ResolvedIndex) = 0 then #table(
            List.Union({Cols, List.Transform(IdentitySpecs, each _{0})}), {})
        else Table.FromRecords(
            List.Transform(Table.ToRecords(Normalised), (row) =>
                Record.Combine({row, [
                    PersonId = Record.Field(ResolvedIndex, Record.Field(Labels, KeysFor(row){0})),
                    UserPrincipalName = Value(row, IdentityColumns{0}),
                    EntraId = Value(row, IdentityColumns{2}),
                    PeopleHistoricalId = Value(row, IdentityColumns{3})
                ]})),
            List.Union({Cols, List.Transform(IdentitySpecs, each _{0})}), MissingField.UseNull),
    Renamed = Table.RenameColumns(WithPid, {
        {"Session count","SessionCount"},
        {"Spending policy limit","SpendingPolicyLimit"},
        {"Total Copilot Credits used","CreditsUsed"},
        {"User limit","UserLimit"}
    }, MissingField.Ignore),
    Cols2 = Table.ColumnNames(Renamed),
    Find2 = (aliases as list) as nullable text =>
        List.First(List.Select(Cols2, each List.Contains(aliases, Key(_))), null),
    PolNameCol = Find2({"policyname", "spendingpolicyname"}),
    PolSvcCol = Find2({"policyservicesincluded", "includedservices"}),
    PolLimCol = Find2({"policylimit"}),
    WithPolName = if PolNameCol = null then Table.AddColumn(Renamed, "PolicyName", each null, type text)
        else Table.RenameColumns(Renamed, {{PolNameCol, "PolicyName"}}),
    WithPolSvc = if PolSvcCol = null then Table.AddColumn(WithPolName, "IncludedServices", each null, type text)
        else Table.RenameColumns(WithPolName, {{PolSvcCol, "IncludedServices"}}),
    WithPlanLim = if PolLimCol = null or List.Contains(Table.ColumnNames(WithPolSvc), "SpendingPolicyLimit")
        then WithPolSvc
        else Table.RenameColumns(WithPolSvc, {{PolLimCol, "SpendingPolicyLimit"}}),
    // Pad the required metrics without discarding inline custom organisation fields.
    Kept = Table.SelectColumns(WithPlanLim, List.Union({
        {
            "PersonId","UserPrincipalName","PeopleHistoricalId","EntraId",
            "ServiceId","ServiceName","SpendingPolicyId","MetricDate",
            "SessionCount","SpendingPolicyLimit","CreditsUsed","UserLimit",
            "PolicyName","IncludedServices"
        },
        Table.ColumnNames(WithPlanLim)
    }), MissingField.UseNull),
    Typed = Table.TransformColumnTypes(Kept, {
        {"PersonId", type text},
        {"UserPrincipalName", type text},
        {"PeopleHistoricalId", type text},
        {"EntraId", type text},
        {"ServiceId", type text},
        {"ServiceName", type text},
        {"SpendingPolicyId", type text},
        {"MetricDate", type date},
        {"SessionCount", Int64.Type},
        {"SpendingPolicyLimit", Int64.Type},
        {"CreditsUsed", type number},
        {"UserLimit", Int64.Type},
        {"PolicyName", type text},
        {"IncludedServices", type text}
    })
in
    Typed
