// Illustrative fictional scenarios for Contradiction Detection & Narrative Divergence Radar
// Note: All companies, ticker symbols, and news outlets below are explicitly FICTIONAL
// to demonstrate multi-perspective narrative divergence without fabricating quotes for real entities.
export const MOCK_CONTRADICTION_SCENARIOS = {
  "meridian-nickel": {
    id: "meridian-nickel",
    ticker: "MNKL",
    company: "Meridian Alloy Corp (Fictional Demo)",
    eventTitle: "Kuala Industrial Park Smelter Incident & EV Nickel Supply",
    date: "Illustrative Scenario",
    severity: "critical",
    summary: "A fictionalized supply-chain case study demonstrating how global financial wires, local industrial-park reporting, and corporate press releases diverge during a localized smelter outage.",
    perspectives: {
      western_media: {
        source: "GlobalWire Financial (Fictional)",
        headline: "Meridian Alloy Smelter Outage Halts Complex Output, Threatening Regional Battery Supply",
        publishedAt: "Illustrative T+2h",
        stance: "Macro Risk Alarm / Bearish",
        stanceColor: "#ef4444",
        biasProfile: "Amplifies systemic commodities supply shocks and headline volatility.",
        claims: [
          "Entire smelting complex shut down indefinitely following an industrial incident.",
          "Regional energy regulators preparing broad safety suspension of export quotas.",
          "Downstream battery producers face immediate raw material rationing."
        ]
      },
      local_media: {
        source: "Archipelago Industrial Gazette (Fictional · Translated)",
        headline: "Auxiliary Transformer Fire at Line 3 Contained in 2 Hours; Plant Union Requests 24h Safety Review",
        publishedAt: "Illustrative T+0h",
        stance: "Localized Safety / Labor Incident",
        stanceColor: "#10b981",
        biasProfile: "Focuses on on-the-ground worker safety, municipal emergency logs, and union shift schedules.",
        claims: [
          "Incident confined strictly to an auxiliary transformer on Furnace Line 3; Lines 1, 2, and 4 remain operational.",
          "Zero fatalities reported; 4 technicians treated for minor injuries.",
          "Local labor committee requested a 24-hour safety inspection before restarting Line 3."
        ]
      },
      corporate_pr: {
        source: "Meridian Alloy Investor Relations (Fictional)",
        headline: "Controlled Thermal Anomaly Managed via Automated Suppression; Quarterly Shipments Intact",
        publishedAt: "Illustrative T+4h",
        stance: "Damage Control / Minimizing Impact",
        stanceColor: "#8b5cf6",
        biasProfile: "Minimizes downtime, protects valuation, and reassures institutional off-takers.",
        claims: [
          "Automated suppression neutralized the thermal event within 35 minutes.",
          "No structural damage sustained by primary smelting kilns.",
          "All quarterly off-take contracts remain on schedule using buffer inventory."
        ]
      }
    },
    contradictions: [
      {
        id: "c1",
        dimension: "Operational Disruption Scope",
        severity: "critical",
        westernClaim: "Halts entire industrial park output indefinitely, triggering supply shortages.",
        localClaim: "Confined strictly to Line 3; Lines 1, 2, and 4 (75% capacity) operating normally.",
        corporateClaim: "Minor localized thermal event; automated systems functioned; deliveries intact.",
        synthesis: "Global wire coverage conflated the entire industrial complex with a single auxiliary line, while on-ground reporting indicates 75% of smelting capacity remains active.",
        groundTruthStatus: "verified_local"
      },
      {
        id: "c2",
        dimension: "Recovery Timeline & Regulatory Risk",
        severity: "moderate",
        westernClaim: "Indefinite shutdown awaiting federal safety investigation and potential export sanctions.",
        localClaim: "Union requesting a 24-hour safety review; municipal inspectors already on site.",
        corporateClaim: "Full operational resumption across Line 3 within 48 hours.",
        synthesis: "Local safety review timelines point to a 3–4 day restart window for Line 3—longer than Corporate PR's 48-hour target, but far short of an indefinite shutdown.",
        groundTruthStatus: "disputed_timeline"
      }
    ],
    epistemicVerdict: {
      consensusFacts: [
        "An auxiliary transformer fault occurred on Furnace Line 3.",
        "Automated fire suppression deployed with zero fatalities.",
        "Lines 1, 2, and 4 remained operational."
      ],
      spinAnalysis: "Global wires amplified worst-case disruption framing, Corporate PR downplayed union inspection delays, and local industrial reporting provided granular line-level status.",
      marketAlpha: "Illustrative takeaway: Separates localized 1-line downtime (25% capacity for 3–4 days) from systemic multi-month outage narratives. Not investment advice."
    }
  },
  "vanguard-mobility": {
    id: "vanguard-mobility",
    ticker: "VMSX",
    company: "Vanguard Mobility Systems (Fictional Demo)",
    eventTitle: "Driver-Assist Regulatory Inquiry & Highway Incident",
    date: "Illustrative Scenario",
    severity: "high",
    summary: "A fictionalized regulatory-news case study showing how national headlines, municipal police logs, and automaker telemetry statements frame the same event differently.",
    perspectives: {
      western_media: {
        source: "Continental Markets Daily (Fictional)",
        headline: "Safety Agency Opens Probe Into Vanguard Mobility Driver-Assist Software",
        publishedAt: "Illustrative T+6h",
        stance: "Regulatory Scrutiny / Bearish",
        stanceColor: "#ef4444",
        biasProfile: "Focuses on potential fleetwide recall liabilities and regulatory risk.",
        claims: [
          "Driver-assist vision module allegedly failed to detect hazard lighting in low-visibility conditions.",
          "Regulators evaluating whether a software recall is warranted.",
          "Commentary highlights potential warranty and legal overhang."
        ]
      },
      local_media: {
        source: "Central Valley Metro Chronicle (Fictional)",
        headline: "Highway Patrol Blotter: Driver Cited for Impairment; Vehicle Telemetry Under Review",
        publishedAt: "Illustrative T+1h",
        stance: "Factual Police Blotter",
        stanceColor: "#10b981",
        biasProfile: "Reports municipal police findings, toxicology logs, and road-condition records.",
        claims: [
          "Driver was cited on suspicion of impaired driving at the scene.",
          "Police report notes driver was inattentive prior to impact.",
          "Incident remains part of a standard multi-agency collision review."
        ]
      },
      corporate_pr: {
        source: "Vanguard Mobility Safety Bureau (Fictional)",
        headline: "Vehicle Telemetry Shows Repeated Driver Warnings & Manual Pedal Override",
        publishedAt: "Illustrative T+8h",
        stance: "Technical Exoneration",
        stanceColor: "#8b5cf6",
        biasProfile: "Uses proprietary telemetry logs to shift focus toward human driver intervention.",
        claims: [
          "Onboard logs show multiple visual and audio hands-on-wheel alerts prior to the event.",
          "Manual accelerator input overrode automated braking 1.4 seconds before impact.",
          "Company received a routine information request with no recall notice issued."
        ]
      }
    },
    contradictions: [
      {
        id: "c1",
        dimension: "Primary Cause & Regulatory Scope",
        severity: "high",
        westernClaim: "Software vision failure prompting imminent fleetwide recall.",
        localClaim: "Impaired driver cited; standard multi-agency collision review underway.",
        corporateClaim: "Manual driver pedal override; routine regulatory data request only.",
        synthesis: "National coverage omitted driver impairment and manual override details while characterizing a preliminary information request as an imminent recall.",
        groundTruthStatus: "regulatory_mischaracterization"
      }
    ],
    epistemicVerdict: {
      consensusFacts: [
        "A highway collision involving a Vanguard Mobility vehicle occurred.",
        "Safety regulators requested telemetry logs as part of a preliminary review.",
        "Local authorities cited the driver at the scene."
      ],
      spinAnalysis: "National financial press emphasized systemic recall risk, while corporate PR emphasized driver override to deflect broader ADAS scrutiny.",
      marketAlpha: "Illustrative takeaway: Distinguishes routine preliminary regulatory information requests from confirmed recall orders. Not investment advice."
    }
  },
  "apex-devices": {
    id: "apex-devices",
    ticker: "ACDX",
    company: "Apex Consumer Devices (Fictional Demo)",
    eventTitle: "Seasonal Assembly Campus Staffing Dispute",
    date: "Illustrative Scenario",
    severity: "medium",
    summary: "A fictionalized supply-chain staffing scenario contrasting international holiday-quarter fears with provincial mediation reports and corporate multi-sourcing statements.",
    perspectives: {
      western_media: {
        source: "Transatlantic Business Wire (Fictional)",
        headline: "Apex Devices Faces Holiday Shipment Crunch Amid Contract Assembly Dispute",
        publishedAt: "Illustrative T+12h",
        stance: "Revenue Threat / Bearish",
        stanceColor: "#ef4444",
        biasProfile: "Emphasizes quarterly revenue misses and consumer delivery delays.",
        claims: [
          "Premium handset assembly output estimated down up to 30%.",
          "Seasonal staffing departures threaten holiday delivery targets.",
          "Consensus revenue estimates flagged as at risk."
        ]
      },
      local_media: {
        source: "Provincial Economic Post (Fictional · Translated)",
        headline: "Industrial Zone Mediates Onboarding Stipend Dispute; 85%+ Shift Attendance Maintained",
        publishedAt: "Illustrative T+4h",
        stance: "Regional Labor Mediation",
        stanceColor: "#10b981",
        biasProfile: "Focuses on local hiring bonuses, mediation outcomes, and campus attendance.",
        claims: [
          "Dispute centered on onboarding stipends for seasonal recruits and was settled within 36 hours.",
          "Automated final-assembly lines continued operating across weekend shifts.",
          "Over 85% of scheduled assembly staff remained active on site."
        ]
      },
      corporate_pr: {
        source: "Apex Devices Corporate Communications (Fictional)",
        headline: "Multi-Region Manufacturing Network Keeps Holiday Delivery Windows On Track",
        publishedAt: "Illustrative T+16h",
        stance: "Supply Chain Flexibility",
        stanceColor: "#8b5cf6",
        biasProfile: "Highlights geographic redundancy and unchanged customer lead times.",
        claims: [
          "Primary campus output remains aligned with seasonal targets.",
          "Secondary regional assembly hubs absorbed incremental throughput.",
          "Published customer delivery estimates remain unchanged."
        ]
      }
    },
    contradictions: [
      {
        id: "c1",
        dimension: "Workforce Disruption Extent",
        severity: "high",
        westernClaim: "Walkout paralyzes plant with 30% output lost.",
        localClaim: "Seasonal stipend dispute resolved in 36 hours; 85%+ attendance maintained.",
        corporateClaim: "Multi-region sourcing absorbs regional staffing fluctuations.",
        synthesis: "International coverage conflated seasonal recruit turnover with a prolonged campus-wide shutdown.",
        groundTruthStatus: "verified_local"
      }
    ],
    epistemicVerdict: {
      consensusFacts: [
        "An onboarding stipend dispute occurred among seasonal assembly recruits.",
        "Local mediators facilitated a compensation settlement.",
        "Apex Devices operates assembly capacity across multiple regions."
      ],
      spinAnalysis: "International wires projected multi-week stockouts while corporate PR minimized short-term staffing friction.",
      marketAlpha: "Illustrative takeaway: Short-duration (<48h) seasonal staffing disputes rarely produce multi-week shipment collapses when attendance stays above 85%. Not investment advice."
    }
  }
}
