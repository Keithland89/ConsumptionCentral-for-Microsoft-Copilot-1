let
    Tbl = GetTable("org_attributes"),
    Result =
        if Tbl = null or Table.IsEmpty(Tbl) then null
        else
            let
                Typed = Table.TransformColumnTypes(Tbl,
                    List.Transform(Table.ColumnNames(Tbl), each {_, type text})),
                Trimmed = Table.TransformColumns(Typed,
                    List.Transform(Table.ColumnNames(Typed), each
                        {_, (v) => if v = null then null else Text.Trim(Text.From(v)), type nullable text}))
            in
                Trimmed
in
    Result
