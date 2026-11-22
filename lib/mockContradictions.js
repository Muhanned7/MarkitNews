// Comprehensive mock datasets for Contradiction Detection & Narrative Divergence Radar
export const MOCK_CONTRADICTION_SCENARIOS = {
  "tsingshan-nickel": {
    id: "tsingshan-nickel",
    ticker: "NICKEL",
    company: "PT Tsingshan / Global EV Supply Chain",
    eventTitle: "Sulawesi Smelter Explosion & Global EV Nickel Supply",
    date: "14 hours ago",
    severity: "critical",
    summary: "Breaking reports surfaced of a fire at a major Indonesian nickel processing facility, sparking conflicting narratives on global EV battery supply disruption.",
    perspectives: {
      western_media: {
        source: "Bloomberg / Financial Times",
        headline: "Indonesian Smelter Blast Halts Output, Threatening Global EV Supply Chains",
        publishedAt: "14 hours ago",
        stance: "Macro Risk Alarm / Bearish",
        stanceColor: "#ef4444",
        biasProfile: "Amplifies systemic commodities supply shocks and algorithmic market contagion.",
        claims: [
          "Complex shut down indefinitely following catastrophic explosion.",
          "Indonesian Ministry of Energy preparing nationwide safety suspension of export quotas.",
          "Global EV battery producers face immediate raw material rationing and spot price spikes."
        ]
      },
      local_media: {
        source: "Antara News / Radar Sulteng (Translated)",
        headline: "Transformer Fire at Morowali Industrial Park Line 3 Extinguished in 2 Hours; Union Demands 24h Review",
        publishedAt: "16 hours ago",
        stance: "Localized Safety / Labor Incident",
        stanceColor: "#10b981",
        biasProfile: "Focuses on on-the-ground worker safety, municipal police blotter, and local union bargaining.",
        claims: [
          "Incident strictly confined to auxiliary transformer at Furnace Line 3; Lines 1, 2, and 4 continue normal operations.",
          "Zero fatalities reported; 4 contract technicians treated for minor non-life-threatening flash burns.",
          "Regional labor union staging a voluntary 24-hour shift pause to review emergency ventilation."
        ]
      },
      corporate_pr: {
        source: "PT Tsingshan Investor Relations & Press Bureau",
        headline: "Controlled Thermal Anomaly Managed with Automated Safety Protocols; Delivery Schedule Intact",
        publishedAt: "12 hours ago",
        stance: "Damage Control / Minimizing Impact",
        stanceColor: "#8b5cf6",
        biasProfile: "Minimizes downtime, protects quarterly stock valuation, and reassures institutional off-takers.",
        claims: [
          "Automated dry-chemical suppression neutralized thermal variation within 35 minutes.",
          "Zero structural damage sustained by primary rotary kiln or smelting furnaces.",
          "All Q3 and Q4 off-take delivery contracts remain 100% on schedule with buffer inventory."
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
        synthesis: "Western media conflated the entire Morowali complex with a single auxiliary furnace line. Physical reality shows 75% of production is completely operational.",
        groundTruthStatus: "verified_local"
      },
      {
        id: "c2",
        dimension: "Human & Physical Damage",
        severity: "high",
        westernClaim: "Catastrophic explosion with unconfirmed major casualties and extensive furnace collapse.",
        localClaim: "Transformer electrical fire; 4 workers treated for minor burns; no fatalities.",
        corporateClaim: "Zero structural damage; standard occupational safety protocols triggered.",
        synthesis: "Local hospital and police logs confirm no fatalities and minimal injuries. Western wire reports relied on unverified social media speculation.",
        groundTruthStatus: "verified_local"
      },
      {
        id: "c3",
        dimension: "Recovery Timeline & Regulatory Risk",
        severity: "moderate",
        westernClaim: "Indefinite shutdown awaiting federal safety investigation and potential export sanctions.",
        localClaim: "Union demanding 24-hour safety review; local inspectors already on site.",
        corporateClaim: "Full operational resumption across Line 3 within 48 hours.",
        synthesis: "Local labor union negotiations will likely delay Line 3 restart by 3 to 4 days, making Corporate PR\'s 48-hour estimate overly optimistic, but Western media\'s \'indefinite shutdown\' completely inaccurate.",
        groundTruthStatus: "disputed_timeline"
      }
    ],
    epistemicVerdict: {
      consensusFacts: [
        "A thermal transformer failure occurred at Furnace Line 3 at approximately 04:15 local time.",
        "Automated fire suppression deployed successfully with no fatalities.",
        "Lines 1, 2, and 4 continue normal operations."
      ],
      spinAnalysis: "Western media amplified worst-case scenario language to generate clicks and feed algorithmic commodities volatility. Corporate PR minimized legitimate union safety concerns. Local reporting provided the only grounded physical inventory.",
      marketAlpha: "The 5.2% selloff in downstream EV battery stocks is an overreaction driven by faulty Western wire reports. Strong risk-reward buy opportunity before wire corrections emerge."
    }
  },
  "tsla-autopilot": {
    id: "tsla-autopilot",
    ticker: "TSLA",
    company: "Tesla Inc.",
    eventTitle: "Federal Autopilot Safety Probe & Fatal Highway Collision",
    date: "1 day ago",
    severity: "high",
    summary: "Conflicting accounts of a highway collision involving Full Self-Driving (FSD) and an emergency vehicle spark regulatory and legal crossfire.",
    perspectives: {
      western_media: {
        source: "The Wall Street Journal / Reuters",
        headline: "NHTSA Opens Probe as Tesla FSD Reportedly Linked to Fatal Emergency Vehicle Crash",
        publishedAt: "1 day ago",
        stance: "Regulatory Scrutiny / Bearish",
        stanceColor: "#ef4444",
        biasProfile: "Focuses on potential national recall liabilities and CEO regulatory clashes.",
        claims: [
          "FSD hardware failed to detect flashing emergency vehicle lights in low-light conditions.",
          "NHTSA considering mandatory nationwide recall or software suspension.",
          "Analyst estimates model a $1.2B legal and warranty headwind."
        ]
      },
      local_media: {
        source: "California Highway Patrol Blotter & Sacramento Bee",
        headline: "CHP Report: Driver in Highway 99 Crash Had High Blood Alcohol Content; FSD Telemetry Pending",
        publishedAt: "1 day ago",
        stance: "Factual Crime / Accident Blotter",
        stanceColor: "#10b981",
        biasProfile: "Reports local police findings, toxicology results, and road condition logs.",
        claims: [
          "Driver was arrested on suspicion of DUI with BAC measured at 0.14%.",
          "Police report states driver hands were not on steering wheel for over 3 minutes prior to impact.",
          "Emergency vehicle was parked halfway into active traffic lane around a blind turn with no flares."
        ]
      },
      corporate_pr: {
        source: "Tesla Official Safety Report & IR Release",
        headline: "Vehicle Telemetry Confirms Driver Override & Seatbelt Interlock Warnings Prior to Incident",
        publishedAt: "20 hours ago",
        stance: "Technical Exoneration / Defiant",
        stanceColor: "#8b5cf6",
        biasProfile: "Leverages proprietary telemetry data to deflect systemic liability toward human driver culpability.",
        claims: [
          "Onboard logs show Autopilot issued 6 visual and audio hands-on-wheel warnings within 90 seconds.",
          "Accelerator pedal was manually depressed by driver 1.4 seconds before impact, overriding automatic braking.",
          "Tesla FSD safety statistics remain 8.4x safer than US average vehicle miles traveled."
        ]
      }
    },
    contradictions: [
      {
        id: "c1",
        dimension: "Primary Cause & Fault",
        severity: "critical",
        westernClaim: "FSD computer vision failure unable to detect flashing emergency beacons.",
        localClaim: "Driver heavily intoxicated (0.14 BAC) with hands off controls around unlit blind turn.",
        corporateClaim: "Driver manually depressed accelerator pedal, overriding automatic safety braking.",
        synthesis: "Western media omitted driver intoxication and manual pedal override to focus solely on autonomous AI culpability.",
        groundTruthStatus: "verified_telemetry"
      },
      {
        id: "c2",
        dimension: "Regulatory Recall Threat",
        severity: "high",
        westernClaim: "Federal regulators preparing imminent fleetwide recall and potential hardware retrofits.",
        localClaim: "Standard multi-agency collision review following any incident involving first responders.",
        corporateClaim: "Routine information request received from NHTSA with zero recall notices issued.",
        synthesis: "While NHTSA has opened a preliminary evaluation, Western media sensationalized a routine information request as an \'imminent recall\'.",
        groundTruthStatus: "regulatory_mischaracterization"
      }
    ],
    epistemicVerdict: {
      consensusFacts: [
        "A collision involving a Tesla vehicle and a stationary police cruiser occurred.",
        "NHTSA has requested vehicle logs as part of its ongoing ADAS audit.",
        "The driver was taken into custody by local authorities."
      ],
      spinAnalysis: "Mainstream financial outlets downplayed clear driver criminal negligence to generate autonomous driving fear; Tesla PR leveraged proprietary telemetry to completely absolve hardware design.",
      marketAlpha: "Headline volatility creates temporary price discounts; regulatory recall risk is remote given verified driver override."
    }
  },
  "aapl-foxconn": {
    id: "aapl-foxconn",
    ticker: "AAPL",
    company: "Apple Inc. / Foxconn",
    eventTitle: "Zhengzhou Assembly Facility Walkout & iPhone 16 Delays",
    date: "2 days ago",
    severity: "medium",
    summary: "Western reports of a catastrophic iPhone supply chain collapse clash with local provincial labor reports and Apple\'s supply chain adjustments.",
    perspectives: {
      western_media: {
        source: "CNBC / Financial Times",
        headline: "Apple Faces Holiday Quarter Crisis as Key Foxconn Factory Paralyzed by Discontent",
        publishedAt: "2 days ago",
        stance: "Revenue Threat / Bearish",
        stanceColor: "#ef4444",
        biasProfile: "Emphasizes consumer holiday stockouts and quarterly EPS misses.",
        claims: [
          "Production cut by up to 30% across premium iPhone models.",
          "Over 20,000 workers left facility following wage disputes.",
          "Apple likely to miss holiday revenue consensus by $4.5 Billion."
        ]
      },
      local_media: {
        source: "Henan Daily & South China Morning Post",
        headline: "Zhengzhou Industrial Park Resolves Contract Discrepancy with Bonus Settlement; Over 85% Attendance",
        publishedAt: "2 days ago",
        stance: "Industrial Peace / Regional Economy",
        stanceColor: "#10b981",
        biasProfile: "Focuses on provincial government mediation, hiring bonuses, and factory stability.",
        claims: [
          "Dispute involved onboarding allowance for new seasonal recruits, resolved in 36 hours with a 1,000 RMB stipend.",
          "Key automated assembly lines maintained continuous operations throughout the weekend.",
          "Over 180,000 workers actively on site with recruitment targets 92% fulfilled."
        ]
      },
      corporate_pr: {
        source: "Foxconn Technology Group & Apple PR",
        headline: "Facility Operating Smoothly; Global Multi-Sourcing Strategy Ensures Delivery Commitments",
        publishedAt: "1 day ago",
        stance: "Supply Chain Flexibility",
        stanceColor: "#8b5cf6",
        biasProfile: "Highlights global manufacturing redundancy (India, Vietnam) and seamless inventory.",
        claims: [
          "Zhengzhou campus production targets are on track with normal seasonal output.",
          "Indian manufacturing hubs expanded throughput to offset regional capacity shifts.",
          "Customer estimated delivery dates for flagship models unchanged."
        ]
      }
    },
    contradictions: [
      {
        id: "c1",
        dimension: "Workforce Disruption Extent",
        severity: "high",
        westernClaim: "Mass walkout paralyzes plant with 30% output wiped out.",
        localClaim: "Seasonal bonus dispute resolved within 36 hours; 85%+ workforce remained on lines.",
        corporateClaim: "Production operates normally; global multi-sourcing cushions all regional shifts.",
        synthesis: "Western reporting mistook seasonal turnover of contract recruits for an existential manufacturing shutdown.",
        groundTruthStatus: "verified_local"
      }
    ],
    epistemicVerdict: {
      consensusFacts: [
        "A bonus payment dispute occurred among new seasonal recruits.",
        "Provincial mediators facilitated a compensation agreement.",
        "Apple has active supply chain capacity in both China and India."
      ],
      spinAnalysis: "Western media amplified holiday stockout panic; Foxconn PR obscured real labor tensions by pointing to Indian diversification.",
      marketAlpha: "Holiday delivery delays are minor (1-2 days) rather than catastrophic multi-week stockouts."
    }
  }
}
