"""Check shipped Azure input contracts without refreshing or changing a PBIT."""
import json
import re
import zipfile
from pathlib import Path

from check_pbit_defaults import decode


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = {
    "AzureAiSpend": {
        "UsageDate", "ServiceName", "Meter", "ResourceName", "ResourceGroup",
        "Cost", "UsageQuantity", "DepartmentTag", "Currency",
    },
    "AzureAiTokens": {
        "Date", "ResourceName", "ResourceGroup", "Deployment", "Metric", "Value",
    },
}


def text(expression):
    return "\n".join(expression) if isinstance(expression, list) else expression


def check():
    for folder, label in (
        ("1. Local CSV", "Local CSV"),
        ("2. Fabric", "Fabric"),
        ("3. Viva Direct", "Viva Direct"),
    ):
        path = ROOT / folder / f"Consumption Central - {label}.pbit"
        with zipfile.ZipFile(path) as package:
            assert package.testzip() is None, f"Invalid ZIP: {path}"
            model = json.loads(decode(package.read("DataModelSchema")))["model"]
        tables = {table["name"]: table for table in model["tables"]}
        expressions = {item["name"]: text(item["expression"])
                       for item in model.get("expressions", [])}
        for name, columns in CONTRACTS.items():
            table = tables[name]
            actual_columns = {column["name"] for column in table["columns"]}
            assert columns <= actual_columns, (label, name, columns - actual_columns)
            partition = table["partitions"][0]["source"]
            assert partition["type"] == "m", (label, name, partition["type"])
            query = text(partition["expression"])
            for column in columns:
                assert f'"{column.lower()}"' in query, (label, name, column, "missing input alias")
            if label == "Fabric":
                source = "azure_ai_spend" if name == "AzureAiSpend" else "azure_ai_tokens"
                assert re.search(r'GetTable\(\s*"' + source + r'"\s*\)', query)
                assert "FabricSource" in expressions["GetTable"]
                assert "Sql.Database(FabricSQLEndpoint, LakehouseName)" in expressions["FabricSource"]
                assert '"dbo"' in expressions["GetTable"]
            else:
                filename = "azureaispenddaily" if name == "AzureAiSpend" else "azureaitokensdaily"
                assert "GetDataFile(" in query and f'"{filename}"' in query
                assert "DataFolder" in expressions["DataFiles"]
        assert "AzureAiDeployments" not in tables, "Update the documented inventory support"
        print(f"{label}: canonical Azure spend/metrics reader contracts match")
    print("Static contract check only; no M execution, Azure calls or Service refresh.")


if __name__ == "__main__":
    check()
