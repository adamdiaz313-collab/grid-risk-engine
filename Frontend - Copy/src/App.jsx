import React, { useState } from "react";
import "./App.css";

function Card({ children }) {
  return <div className="card">{children}</div>;
}

function getRiskStyle(probability) {
  if (probability < 20) {
    return {
      label: "Low Risk",
      message: "Conditions are mostly stable right now.",
      color: "#059669",
      advice:
        "No major outage signals are active. Continue monitoring local utility updates if weather changes.",
    };
  }

  if (probability < 45) {
    return {
      label: "Moderate Risk",
      message: "Some conditions are adding stress to the grid.",
      color: "#d97706",
      advice:
        "Keep devices charged and monitor local conditions, especially if wind or precipitation increases.",
    };
  }

  if (probability < 70) {
    return {
      label: "High Risk",
      message: "Multiple factors are increasing outage risk.",
      color: "#ea580c",
      advice:
        "Prepare for possible service disruption. Charge devices, check flashlights, and monitor utility alerts.",
    };
  }

  return {
    label: "Severe Risk",
    message: "Outage conditions are strongly elevated.",
    color: "#dc2626",
    advice: "Treat this as an elevated risk period and follow official alerts.",
  };
}

function RiskGauge({ probability, risk }) {
  const safeProbability = Math.max(0, Math.min(100, Number(probability) || 0));
  const rotation = -90 + (safeProbability / 100) * 180;

  return (
    <div className="gauge-wrap">
      <div className="gauge-bg" />
      <div
        className="gauge-fill"
        style={{ borderColor: risk.color, width: `${safeProbability}%` }}
      />
      <div className="needle" style={{ transform: `rotate(${rotation}deg)` }} />
      <div className="needle-dot" />
      <div className="gauge-text">
        <div className="percent">{safeProbability.toFixed(1)}%</div>
        <div
          className="risk-badge"
          style={{ color: risk.color, borderColor: risk.color }}
        >
          {risk.label}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ icon, label, value, subtext }) {
  return (
    <div className="metric">
      <div className="metric-label">
        <span>{icon}</span> {label}
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-subtext">{subtext}</div>
    </div>
  );
}

function MapPreview({ result }) {
  if (!result) {
    return (
      <div className="map-empty">
        <div className="map-icon">⌖</div>
        <h3>Location map appears here</h3>
        <p>
          Search a ZIP code, city, or neighborhood to zoom into the area being
          evaluated.
        </p>
      </div>
    );
  }

  const lat = Number(result.location.latitude);
  const lon = Number(result.location.longitude);
  const delta = 0.035;
  const bbox = `${lon - delta},${lat - delta},${lon + delta},${lat + delta}`;
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat},${lon}`;

  return (
    <div className="map-card">
      <iframe title="location map" src={src} />
      <div className="map-caption">
        <strong>{result.location.display_name}</strong>
        <span>
          {lat.toFixed(4)}, {lon.toFixed(4)} · {result.region} · {result.season}
        </span>
      </div>
    </div>
  );
}

export default function App() {
  const [locationQuery, setLocationQuery] = useState("10032");
  const [peakDemandMw, setPeakDemandMw] = useState("54000");
  const [showAdvancedInput, setShowAdvancedInput] = useState(false);
  const [showAdvancedDetails, setShowAdvancedDetails] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function handlePrediction() {
    try {
      setLoading(true);
      setError("");
      setResult(null);

      const response = await fetch("http://127.0.0.1:8000/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          location_query: locationQuery,
          peak_demand_mw: Number(peakDemandMw || 54000),
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => null);
        throw new Error(
          errData?.detail || "Prediction server did not return a valid response."
        );
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(
        err.message ||
          "Could not connect to the prediction backend. Make sure FastAPI is running on port 8000."
      );
    } finally {
      setLoading(false);
    }
  }

  const risk = result ? getRiskStyle(result.outage_probability) : null;

  return (
    <div className="page">
      <nav className="nav">
        <div className="brand">
          <div className="logo">⚡</div>
          <div>
            <div className="brand-title">Grid Risk Engine</div>
            <div className="brand-subtitle">AI-powered outage prediction</div>
          </div>
        </div>

        <div className="status">
          <span className="status-dot" />
          Backend: localhost:8000
        </div>
      </nav>

      <section className="hero">
        <div className="hero-card">
          <div className="tag">Live weather · local risk · model backend</div>

          <h1>Check power outage risk near you.</h1>

          <p>
            Search a ZIP code, city, or neighborhood. Grid Risk Engine pulls
            live weather, evaluates grid stress factors, and estimates the
            probability of an outage.
          </p>

          <div className="search-box">
            <div className="search-row">
              <input
                className="input"
                value={locationQuery}
                onChange={(e) => setLocationQuery(e.target.value)}
                placeholder="Enter ZIP, city, or neighborhood"
              />

              <button
                className="button"
                onClick={handlePrediction}
                disabled={loading || !locationQuery.trim()}
              >
                {loading ? "Checking..." : "Check risk"}
              </button>
            </div>

            <button
              className="text-button"
              onClick={() => setShowAdvancedInput(!showAdvancedInput)}
            >
              {showAdvancedInput ? "Hide advanced settings" : "Show advanced settings"}
            </button>

            {showAdvancedInput && (
              <div className="advanced-input">
                <label>Estimated peak demand (MW)</label>
                <input
                  className="input small-input"
                  type="number"
                  value={peakDemandMw}
                  onChange={(e) => setPeakDemandMw(e.target.value)}
                />
                <p>This can later be replaced with real-time ISO or utility demand data.</p>
              </div>
            )}

            {error && <div className="error">{error}</div>}
          </div>
        </div>

        <MapPreview result={result} />
      </section>

      <section className="results">
        <Card>
          {result ? (
            <>
              <div className="risk-header">
                <div>
                  <div className="eyebrow">Current outage risk</div>
                  <h2>{risk.label}</h2>
                </div>
                <div className="source">{result.source}</div>
              </div>

              <RiskGauge probability={result.outage_probability} risk={risk} />

              <div className="meaning">
                <strong>What this means</strong>
                <p>{risk.message}</p>
                <p>
                  <strong>Recommended action:</strong> {risk.advice}
                </p>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">⌁</div>
              <h2>Waiting for a location</h2>
              <p>Run a search to generate a local outage risk score and explanation.</p>
            </div>
          )}
        </Card>

        <div className="details">
          {result ? (
            <>
              <div className="metrics-grid">
                <MetricCard
                  icon="🌡"
                  label="Temperature"
                  value={`${Number(result.weather.temperature_f).toFixed(1)} °F`}
                  subtext="Live weather"
                />

                <MetricCard
                  icon="💨"
                  label="Wind"
                  value={`${Number(result.weather.wind_mph).toFixed(1)} mph`}
                  subtext={`Gusts ${Number(result.weather.wind_gust_mph).toFixed(1)} mph`}
                />

                <MetricCard
                  icon="🌧"
                  label="Rain"
                  value={`${Number(result.weather.precipitation_in).toFixed(2)} in`}
                  subtext={result.storm_active ? "Storm trigger active" : "No storm trigger"}
                />

                <MetricCard
                  icon="⚡"
                  label="Demand"
                  value={`${Number(result.peak_demand_mw).toLocaleString()} MW`}
                  subtext="Estimated load"
                />
              </div>

              <Card>
                <div className="risk-drivers-header">
                  <div>
                    <h3>Risk drivers</h3>
                    <p>These are the active factors contributing to the current score.</p>
                  </div>

                  <button
                    className="advanced-button"
                    onClick={() => setShowAdvancedDetails(!showAdvancedDetails)}
                  >
                    {showAdvancedDetails ? "Hide advanced details" : "Advanced details"}
                  </button>
                </div>

                <div className="driver-tags">
                  {result.drivers?.length ? (
                    result.drivers.map((driver) => <span key={driver}>{driver}</span>)
                  ) : (
                    <span>No major stressors detected</span>
                  )}
                </div>

                {showAdvancedDetails && (
                  <div className="advanced-details">
                    <div><strong>Resolved location:</strong> {result.location.display_name}</div>
                    <div>
                      <strong>Coordinates:</strong>{" "}
                      {Number(result.location.latitude).toFixed(4)}, {" "}
                      {Number(result.location.longitude).toFixed(4)}
                    </div>
                    <div><strong>Region:</strong> {result.region}</div>
                    <div><strong>Season:</strong> {result.season}</div>
                    <div><strong>Humidity:</strong> {Number(result.weather.humidity_percent).toFixed(0)}%</div>
                    <div><strong>Pressure:</strong> {Number(result.weather.pressure_mb).toFixed(1)} mb</div>
                    <div><strong>Weather time:</strong> {result.weather.time}</div>
                    <div><strong>Model source:</strong> {result.source}</div>
                  </div>
                )}
              </Card>
            </>
          ) : (
            <Card>
              <div className="empty-small">
                <div>⚙</div>
                <h3>Weather and model details</h3>
                <p>After a search, this area shows live conditions, risk drivers, and technical details.</p>
              </div>
            </Card>
          )}
        </div>
      </section>
    </div>
  );
}
