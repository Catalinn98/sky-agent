"""
Example: scaffold a project and print the resulting structure.

Run:  python -m sky_agent.examples.scaffold_example
"""

from pathlib import Path
import tempfile
import os

from sky_agent.services.project_scaffold import scaffold_project


def main():
    # Simulate what SKY Workspace sends after project creation
    project_payload = {
        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "project_name": "Acme Corp S/4HANA Migration",
        "project_code": "PRJ_001",
        "systems": [
            {
                "system_id": "sys_ecc_prod",
                "system_name": "ECC Production",
                "system_type": "ECC",
                "role": "source",
                "client": "100",
                "host": "sap-ecc.acme.local",
                "description": "SAP ECC 6.0 EHP8 — Production",
            },
            {
                "system_id": "sys_s4_target",
                "system_name": "S/4HANA Target",
                "system_type": "S4",
                "role": "target",
                "client": "100",
                "host": "sap-s4.acme.local",
                "description": "SAP S/4HANA 2023 — Greenfield",
            },
        ],
        "selected_objects": [
            "cost_center",
            "profit_center",
            "gl_account",
            "supplier",
            "customer",
            "material",
        ],
    }

    # Scaffold into a temp directory (use a real base_dir in production)
    base_dir = Path(tempfile.mkdtemp(prefix="sky_projects_"))

    project_dir = scaffold_project(
        base_dir=base_dir,
        project_id=project_payload["project_id"],
        project_name=project_payload["project_name"],
        project_code=project_payload["project_code"],
        systems=project_payload["systems"],
        selected_objects=project_payload["selected_objects"],
    )

    # Print the tree
    print(f"\n{'='*60}")
    print(f"  Project scaffolded at: {project_dir}")
    print(f"{'='*60}\n")

    for root, dirs, files in os.walk(project_dir):
        level = len(Path(root).relative_to(project_dir).parts)
        indent = "  " * level
        print(f"{indent}{Path(root).name}/")
        for f in sorted(files):
            print(f"{indent}  {f}")


if __name__ == "__main__":
    main()
