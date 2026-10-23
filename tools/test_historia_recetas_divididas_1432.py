"""Prueba de receta A4 con dos mitades distintas sin romper recetas históricas.

Sólo usa pacientes inventados en SQLite temporal: no toca el consultorio ni Neón.
"""
import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "historia-clinica" / "app"))
from fastapi import FastAPI

import documentos_clinicos


class FakeRequest:
    def __init__(self, data):
        self.data = data
    async def json(self):
        return self.data


def route(app, path, method="GET"):
    return next(
        x.endpoint for x in app.routes
        if getattr(x, "path", "") == path and method in getattr(x, "methods", ())
    )


def copies(page):
    main = page.split("<main class='sheet'>", 1)[1].split("</main>", 1)[0]
    left, right = main.split("</section>", 1)[0], main.split("</section>", 1)[1]
    # Sections include nested content? Each half has one section and no nested section.
    assert main.count("<section class='rx-copy") == 2
    left = main.split("<section class='rx-copy", 1)[1].split("</section>", 1)[0]
    right = main.split("<section class='rx-copy", 2)[2].split("</section>", 1)[0]
    return left, right


def main():
    with tempfile.TemporaryDirectory(prefix="receta_1432_") as temp:
        db_path = Path(temp) / "historia.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.executescript("""
                CREATE TABLE patients(
                    id TEXT PRIMARY KEY,name TEXT,national_id TEXT,birth_date TEXT,sex TEXT,deleted_at TEXT
                );
                CREATE TABLE encounters(
                    id TEXT PRIMARY KEY,patient_id TEXT,queue_id TEXT,
                    note_status TEXT,deleted_at TEXT
                );
                INSERT INTO patients(id,name,national_id,birth_date,sex)
                  VALUES('p1','PACIENTE FICTICIO','0000000000','1985-03-02','M');
                INSERT INTO encounters(id,patient_id) VALUES('visit1','p1');
            """)
            conn.commit()
        documentos_clinicos.ensure_schema(db_path)
        app=FastAPI()
        documentos_clinicos.install(app,{
            "DB_PATH":db_path, "ROOT":Path(temp),
            "base":lambda title,body,active:body,
        })
        form = route(app,"/recetas/nueva")("p1").body.decode("utf-8")
        assert "<th>Nombre</th><th>Presentación y cantidad</th><th>Indicaciones</th>" in form
        assert 'class="m-name"' not in form  # input usa HTML con comillas simples
        assert "class='m-name'" in form
        assert "class='m-presentation'" in form
        assert "class='m-indications'" in form
        assert "presentation_quantity:tr.querySelector('.m-presentation').value.trim()" in form
        assert "indications:tr.querySelector('.m-indications').value.trim()" in form

        save = route(app,"/api/recetas","POST")
        data = {
            "patient_id":"p1", "encounter_id":"visit1",
            "issued_date":"2026-10-23", "series_no":"00117",
            "diagnosis":"", "cie10":"", "allergies":"NO",
            "items":[{
                "medication":"AUGMENTIN BID",
                "presentation_quantity":"875/125 TABLETAS X 20",
                "indications":"TOMAR 1 TABLETA CADA 12 HORAS X 10 DIAS",
            }],
            "instructions":"INDICACIONES ADICIONALES DE PRUEBA",
        }
        saved = json.loads(asyncio.run(save(FakeRequest(data))).body)
        assert saved["ok"] and saved["id"]
        with sqlite3.connect(db_path) as conn:
            content = conn.execute("SELECT items_json FROM prescriptions WHERE id=?",
                                   (saved["id"],)).fetchone()[0]
            persisted = json.loads(content)[0]
            assert persisted["medication"] == "AUGMENTIN BID"
            assert persisted["presentation_quantity"] == "875/125 TABLETAS X 20"
            assert persisted["indications"] == "TOMAR 1 TABLETA CADA 12 HORAS X 10 DIAS"

        preview = route(app,"/recetas/{rx_id}/vista")
        page = preview(saved["id"]).body.decode("utf-8")
        left, right = copies(page)
        assert "rx-copy-v2" in left and "rx-copy-v2" in right
        assert "1. AUGMENTIN BID" in left and "1. AUGMENTIN BID" in right
        assert "875/125 TABLETAS X 20" in left
        # Izquierda: nombre y presentación juntos dentro de UN solo
        # bloque en negrita; jamás bajo .med-line.
        assert "1. AUGMENTIN BID <span class='med-presentation'>875/125 TABLETAS X 20</span></div>" in left
        assert "<div class='med-line'>" not in left
        assert "<div class='med-name'>1. AUGMENTIN BID</div>" in right
        assert "<div class='med-line'>TOMAR 1 TABLETA CADA 12 HORAS X 10 DIAS</div>" in right
        assert ".med-presentation{font-weight:900}" in page
        assert "875/125 TABLETAS X 20" not in right
        assert "TOMAR 1 TABLETA CADA 12 HORAS X 10 DIAS" in right
        assert "TOMAR 1 TABLETA CADA 12 HORAS X 10 DIAS" not in left
        assert "INDICACIONES ADICIONALES DE PRUEBA" in right
        assert "INDICACIONES ADICIONALES DE PRUEBA" not in left
        assert ".rx-copy-v2 .rp{top:82mm}" in page
        assert ".rp{position:absolute;top:75mm;" in page
        # Hoja 210x297 mm. La mitad izquierda conserva margen seguro de 8mm;
        # la derecha gana sólo 2mm, dejando 6mm + 3.5mm de espacio interior.
        # La franja inferior queda a 8mm del borde del papel (292-8+5=289).
        assert "padding:0 6mm 0 8mm;grid-template-columns:97mm 99mm;" in page
        assert "width:97mm;height:292mm;" in page
        assert ".rx-copy:last-child{width:99mm}" in page
        assert "grid-template-columns:97mm 99mm;box-shadow:none" in page
        assert "footer{\n  position:absolute;left:3.5mm;right:3.5mm;bottom:8mm;" in page
        assert "bottom:-5mm;width:100%;height:2.7mm;" in page
        assert "@page{size:A4 portrait;margin:0}" in page
        assert page.count("DR. ARMANDO REVELO") == 2
        assert page.count("Serie No: 00117") == 2
        assert page.count("Telf: 0968840690") == 2
        assert "Izquierda: nombre y presentación/cantidad" in page
        assert "window.print()" in preview(saved["id"],1).body.decode("utf-8")

        # Recetas guardadas antes de esta versión conservan las dos copias idénticas.
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """INSERT INTO prescriptions(
                   id,patient_id,encounter_id,issued_at,series_no,diagnosis,cie10,
                   allergies,allergies_detail,items_json,instructions,
                   created_at,updated_at,deleted_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                ("rx-legacy","p1","visit1","2026-10-20T11:00","00116","","",
                 "NO","",json.dumps([{
                     "medication":"AUGMENTIN BID 875/125 TABLETAS X 20",
                     "dose":"TOMAR 1 TABLETA CADA 12HS X 10 DIAS",
                     "frequency":"","duration":"",
                 }]),"INSTRUCCIONES LEGADAS",
                 "2026-10-20T11:00","2026-10-20T11:00"),
            )
            conn.commit()
        old = preview("rx-legacy").body.decode("utf-8")
        old_left, old_right = copies(old)
        assert old_left == old_right
        assert "rx-copy-v2" not in old_left and "rx-copy-v2" not in old_right
        assert "AUGMENTIN BID 875/125 TABLETAS X 20" in old_left
        assert "TOMAR 1 TABLETA CADA 12HS X 10 DIAS" in old_left
        assert "INSTRUCCIONES LEGADAS" in old_left
        assert ".rp{position:absolute;top:75mm;" in old
        assert "2 recetas iguales" in old
        assert "width:97mm;height:292mm;" in old
        assert ".rx-copy:last-child{width:99mm}" in old
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM prescriptions").fetchone()[0] == 2
        print("HISTORIA_RECETAS_DIVIDIDAS_1432_OK")


if __name__=="__main__":
    main()
