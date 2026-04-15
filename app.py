from flask import Flask, request, redirect, url_for, render_template, flash, Response
from database import get_connection, init_db
from repair_data import GUIDES, SYMPTOMS
from ai_guide import get_repair_guide, get_symptom_causes

app = Flask(__name__)
app.secret_key = "moto-tracker-secret"
app.jinja_env.globals['enumerate'] = enumerate

#--------Bikesss-----------------

@app.route("/")
def index():
    conn = get_connection()
    bikes = conn.execute("SELECT * FROM bikes").fetchall()
    conn.close()
    return render_template("index.html", bikes=bikes)

@app.route("/bikes/add", methods=["GET", "POST"]) 
def add_bike():
    if request.method == "POST":
        name = request.form["name"]
        brand = request.form["brand"]
        engine_cc = request.form["engine_cc"]

        conn = get_connection()
        conn.execute("INSERT INTO bikes (name, brand, engine_cc) VALUES (?, ?, ?)", (name, brand, engine_cc))
        conn.commit()
        conn.close()

        return redirect(url_for("index"))
    return render_template("add_bike.html")



#--------Fuel Logs-----------------

@app.route("/bikes/<int:bike_id>/fuel")
def fuel_logs(bike_id):
    conn = get_connection()

    bike = conn.execute(
        "SELECT * FROM bikes WHERE id = ?", (bike_id,)
    ).fetchone()

    logs = conn.execute(
        "SELECT * FROM fuel_logs WHERE bike_id = ? ORDER BY date DESC",
        (bike_id,)
    ).fetchall()

    conn.close()

    logs_with_efficiency = []

    for i, log in enumerate(logs):
        if i == 0:
            kml = None
        else:
            distance = log["odometer_km"] - logs[i - 1]["odometer_km"]
            kml = round(distance / log["liters"], 2) if log["liters"] > 0 else None

        logs_with_efficiency.append({
            "id": log["id"],
            "date": log["date"],
            "odometer_km": log["odometer_km"],
            "liters": log["liters"],
            "price": log["price"],
            "kml": kml
        })

    # ✅ COMPUTE TOTALS HERE (correct place)
    total_fuel = sum(log["liters"] for log in logs_with_efficiency if log["liters"])

    # Only include positive km/L values (greater than 0)
    kml_values = [log["kml"] for log in logs_with_efficiency if log["kml"] and log["kml"] > 0]
    avg_kml = round(sum(kml_values) / len(kml_values), 2) if kml_values else 0

    return render_template(
        "fuel_logs.html",
        bike=bike,
        logs=logs_with_efficiency,
        total_fuel=total_fuel,
        avg_kml=avg_kml
    )


@app.route("/bikes/<int:bike_id>/fuel/add", methods=["GET", "POST"])
def add_fuel_log(bike_id):
    if request.method == "POST":
        odometer = float(request.form["odometer_km"])
        liters = float(request.form["liters"])
        price = float(request.form["price"]) if request.form["price"] else None
        date = request.form["date"]

        conn = get_connection()
        conn.execute(
            "INSERT INTO fuel_logs (bike_id, odometer_km, liters, price, date) VALUES (?, ?, ?, ?, ?)",
            (bike_id, odometer, liters, price, date)
        )
        conn.commit()
        conn.close()

        flash("Fuel log added!")

        # ✅ redirect ONLY
        return redirect(url_for("fuel_logs", bike_id=bike_id))

    return render_template("add_fuel.html", bike_id=bike_id)
# ── Maintenance Logs ───────────────────────────────

@app.route("/bikes/<int:bike_id>/maintenance")
def maintenance_logs(bike_id):
    conn = get_connection()
    bike = conn.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()
    logs = conn.execute(
        "SELECT * FROM maintenance_logs WHERE bike_id = ? ORDER BY date DESC", (bike_id,)
    ).fetchall()
    conn.close()

    return render_template("maintenance_logs.html", bike=bike, logs=logs)

@app.route("/bikes/<int:bike_id>/maintenance/add", methods=["GET", "POST"])
def add_maintenance_log(bike_id):
    if request.method == "POST":
        type_ = request.form["type"]
        notes = request.form["notes"] or None
        date = request.form["date"]

        conn = get_connection()
        conn.execute(
            "INSERT INTO maintenance_logs (bike_id, type, notes, date) VALUES (?, ?, ?, ?)",
            (bike_id, type_, notes, date)

        )
        conn.commit()
        conn.close()
        flash("Bike added!")
        return redirect(url_for("maintenance_logs", bike_id=bike_id))
    
    return render_template("add_maintenance.html", bike_id=bike_id)


@app.route("/bikes/<int:bike_id>/delete", methods=["POST"])
def delete_bike(bike_id):
    conn = get_connection()
    conn.execute("DELETE FROM fuel_logs WHERE bike_id = ?", (bike_id,))
    conn.execute("DELETE FROM maintenance_logs WHERE bike_id = ?", (bike_id,))
    conn.execute("DELETE FROM bikes WHERE id = ?", (bike_id,))
    conn.commit()
    conn.close()
    flash("Bike added!")  
    return redirect(url_for("index"))


@app.route("/fuel_logs/<int:log_id>/delete", methods=["POST"])
def delete_fuel_log(log_id):
    conn = get_connection()
    bike_id = conn.execute("SELECT bike_id FROM fuel_logs WHERE id = ?", (log_id,)).fetchone()["bike_id"]
    conn.execute("DELETE FROM fuel_logs WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()
    flash("Fuel log deleted!")
    return redirect(url_for("fuel_logs", bike_id=bike_id))


@app.route("/maintenance_logs/<int:log_id>/delete", methods=["POST"])
def delete_maintenance_log(log_id):
    conn = get_connection()
    bike_id = conn.execute("SELECT bike_id FROM maintenance_logs WHERE id = ?", (log_id,)).fetchone()["bike_id"]
    conn.execute("DELETE FROM maintenance_logs WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()
    flash("Maintenance log deleted!")
    return redirect(url_for("maintenance_logs", bike_id=bike_id))

import json

@app.route("/bikes/<int:bike_id>/stats")
def bike_stats(bike_id):
    conn = get_connection()

    bike = conn.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()

    logs = conn.execute(
        "SELECT * FROM fuel_logs WHERE bike_id = ? ORDER BY odometer_km ASC",
        (bike_id,)
    ).fetchall()

    maintenance = conn.execute(
        "SELECT * FROM maintenance_logs WHERE bike_id = ? ORDER BY date ASC",
        (bike_id,)
    ).fetchall()

    conn.close()

    # km/L chart data
    kml_labels = []
    kml_data = []

    # cost chart data
    cost_labels = []
    cost_data = []

    # Calculate totals
    total_fuel = 0
    total_cost = 0
    valid_kml_values = []

    for i, log in enumerate(logs):
        # Add to totals
        if log["liters"]:
            total_fuel += log["liters"]
        if log["price"]:
            total_cost += log["price"]

        # Calculate km/L for chart
        if i == 0:
            continue
        distance = log["odometer_km"] - logs[i - 1]["odometer_km"]
        kml = round(distance / log["liters"], 2) if log["liters"] > 0 else 0
        kml_labels.append(log["date"])
        kml_data.append(kml)
        
        # Collect valid kml for average (positive values only)
        if kml > 0:
            valid_kml_values.append(kml)

        if log["price"]:
            cost_labels.append(log["date"])
            cost_data.append(round(log["price"], 2))

    # Calculate average km/L
    avg_kml = round(sum(valid_kml_values) / len(valid_kml_values), 2) if valid_kml_values else 0

    # maintenance timeline data
    maint_labels = [m["date"] for m in maintenance]
    maint_types  = [m["type"] for m in maintenance]

    return render_template(
        "stats.html",
        bike=bike,
        logs=logs,  # Add this for the template to use
        total_fuel=round(total_fuel, 1),  # Add this
        total_cost=round(total_cost, 2),  # Add this (optional)
        avg_kml=avg_kml,  # Add this
        kml_labels=json.dumps(kml_labels),
        kml_data=json.dumps(kml_data),
        cost_labels=json.dumps(cost_labels),
        cost_data=json.dumps(cost_data),
        maint_labels=json.dumps(maint_labels),
        maint_types=json.dumps(maint_types)
    )

@app.route("/bikes/<int:bike_id>/edit", methods=["GET", "POST"])
def edit_bike(bike_id):
    conn = get_connection()
    bike = conn.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()

    if request.method == "POST":
        name      = request.form["name"]
        brand     = request.form["brand"]
        engine_cc = request.form["engine_cc"]

        conn.execute(
            "UPDATE bikes SET name = ?, brand = ?, engine_cc = ? WHERE id = ?",
            (name, brand, engine_cc, bike_id)
        )
        conn.commit()
        conn.close()
        flash("Bike updated!")
        return redirect(url_for("index"))

    conn.close()
    return render_template("edit_bike.html", bike=bike)

@app.route("/fuel_logs/<int:log_id>/edit", methods=["GET", "POST"])
def edit_fuel_log(log_id):
    conn = get_connection()
    log = conn.execute("SELECT * FROM fuel_logs WHERE id = ?", (log_id,)).fetchone()

    if request.method == "POST":
        odometer = request.form["odometer_km"]
        liters   = request.form["liters"]
        price    = request.form["price"] or None
        date     = request.form["date"]

        conn.execute(
            "UPDATE fuel_logs SET odometer_km=?, liters=?, price=?, date=? WHERE id=?",
            (odometer, liters, price, date, log_id)
        )
        conn.commit()
        flash("Fuel entry updated!")
        bike_id = log["bike_id"]
        conn.close()
        return redirect(url_for("fuel_logs", bike_id=bike_id))

    conn.close()
    return render_template("edit_fuel_log.html", log=log)

@app.route("/maintenance_logs/<int:log_id>/edit", methods=["GET", "POST"])
def edit_maintenance_log(log_id):
    conn = get_connection()
    log = conn.execute("SELECT * FROM maintenance_logs WHERE id = ?", (log_id,)).fetchone()

    if request.method == "POST":
        type_  = request.form["type"]
        notes  = request.form["notes"] or None
        date   = request.form["date"]

        conn.execute(
            "UPDATE maintenance_logs SET type=?, notes=?, date=? WHERE id=?",
            (type_, notes, date, log_id)
        )
        conn.commit()
        flash("Maintenance entry updated!")
        bike_id = log["bike_id"]
        conn.close()
        return redirect(url_for("maintenance_logs", bike_id=bike_id))

    conn.close()
    return render_template("edit_maintenance_log.html", log=log)

# ── Export ─────────────────────────────────────────
@app.route("/bikes/<int:bike_id>/export/fuel")
def export_fuel(bike_id):
    conn = get_connection()
    bike = conn.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()
    logs = conn.execute(
        "SELECT * FROM fuel_logs WHERE bike_id = ? ORDER BY odometer_km ASC",
        (bike_id,)
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Date", "Odometer (km)", "Liters", "Price", "km/L"])

    for i, log in enumerate(logs):
        if i == 0:
            kml = "—"
        else:
            distance = log["odometer_km"] - logs[i - 1]["odometer_km"]
            kml = round(distance / log["liters"], 2) if log["liters"] > 0 else "—"

        writer.writerow([
            log["date"],
            log["odometer_km"],
            log["liters"],
            log["price"] or "",
            kml
        ])

    output.seek(0)
    filename = f"{bike['name'].replace(' ', '_')}_fuel.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/bikes/<int:bike_id>/export/maintenance")
def export_maintenance(bike_id):
    conn = get_connection()
    bike = conn.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()
    logs = conn.execute(
        "SELECT * FROM maintenance_logs WHERE bike_id = ? ORDER BY date ASC",
        (bike_id,)
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Date", "Type", "Notes"])

    for log in logs:
        writer.writerow([log["date"], log["type"], log["notes"] or ""])

    output.seek(0)
    filename = f"{bike['name'].replace(' ', '_')}_maintenance.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
# ── Repair Guide ────────────────────────────────────
# ── Repair Guide ────────────────────────────────────

@app.route("/repair")
@app.route("/repair/<int:bike_id>")
def repair_home(bike_id=None):
    conn = get_connection()
    bikes = conn.execute("SELECT * FROM bikes").fetchall()
    conn.close()
    return render_template("repair_home.html", guides=GUIDES, symptoms=SYMPTOMS, bike_id=bike_id, bikes=bikes)


@app.route("/repair/symptom/<symptom_key>/<int:bike_id>")
def symptom_detail(symptom_key, bike_id):
    symptom = SYMPTOMS.get(symptom_key)
    if not symptom:
        flash("Symptom not found.")
        return redirect(url_for("repair_home"))
    return render_template("symptom_detail.html", symptom=symptom, symptom_key=symptom_key, bike_id=bike_id)

@app.route("/repair/guide/<guide_key>")
def guide_detail(guide_key):
    guide = GUIDES.get(guide_key)
    if not guide:
        flash("Guide not found.")
        return redirect(url_for("repair_home"))

    conn = get_connection()
    bikes = conn.execute("SELECT * FROM bikes").fetchall()
    conn.close()

    return render_template("guide_detail.html", guide=guide, guide_key=guide_key, bikes=bikes)

@app.route("/repair/guide/<guide_key>/log/<int:bike_id>", methods=["POST"])
def log_from_guide(guide_key, bike_id):
    guide = GUIDES.get(guide_key)
    if not guide:
        return redirect(url_for("repair_home"))

    from datetime import date
    conn = get_connection()
    conn.execute(
        "INSERT INTO maintenance_logs (bike_id, type, notes, date) VALUES (?, ?, ?, ?)",
        (bike_id, guide["title"], f"Logged from repair guide", date.today().isoformat())
    )
    conn.commit()
    conn.close()

    flash(f"{guide['title']} logged to your maintenance record!")
    return redirect(url_for("guide_detail", guide_key=guide_key))

# ── AI Repair Guide ─────────────────────────────────

@app.route("/repair/ai/<int:bike_id>", methods=["GET", "POST"])
def ai_repair(bike_id):
    conn = get_connection()
    bike = conn.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()
    conn.close()

    if request.method == "POST":
        problem = request.form["problem"]
        bike_name = f"{bike['brand']} {bike['name']}"
        guide = get_repair_guide(bike_name, problem)
        return render_template("ai_guide.html", guide=guide, bike=bike, problem=problem)

    return render_template("ai_repair.html", bike=bike)


@app.route("/repair/ai/<int:bike_id>/symptom", methods=["POST"])
def ai_symptom(bike_id):
    conn = get_connection()
    bike = conn.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()
    conn.close()

    symptom = request.form["symptom"]
    bike_name = f"{bike['brand']} {bike['name']}"
    causes = get_symptom_causes(bike_name, symptom)

    return render_template("ai_symptom.html", causes=causes, bike=bike, symptom=symptom)


@app.route("/repair/ai/<int:bike_id>/log", methods=["POST"])
def ai_log_repair(bike_id):
    from datetime import date
    title = request.form["title"]
    notes = request.form["notes"]

    conn = get_connection()
    conn.execute(
        "INSERT INTO maintenance_logs (bike_id, type, notes, date) VALUES (?, ?, ?, ?)",
        (bike_id, title, notes, date.today().isoformat())
    )
    conn.commit()
    conn.close()

    flash(f"{title} logged to your maintenance record!")
    return redirect(url_for("index"))

@app.route("/repair/ai/<int:bike_id>/fix/<problem>")
def ai_fix(bike_id, problem):
    conn = get_connection()
    bike = conn.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()
    conn.close()

    bike_name = f"{bike['brand']} {bike['name']}"
    guide = get_repair_guide(bike_name, problem)
    return render_template("ai_guide.html", guide=guide, bike=bike, problem=problem)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)