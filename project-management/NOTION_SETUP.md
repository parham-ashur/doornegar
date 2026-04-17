# Notion workspace setup (one-time, manual)

The Notion MCP integration ("Doornegar") can read and write pages — but only pages that have been **shared with the integration**. Notion does not allow API-created root pages; you must create the root manually.

## Step 1 — Create the root page
1. Open Notion → Doornegar workspace
2. Create a new page titled **"Doornegar — Project Hub"** (📰 icon)
3. At the top-right, click **"..." → Connections → Add connections → Doornegar**

Once that's done, Claude can create child pages, databases, and content automatically.

## Step 2 — Proposed structure (Claude will build this once access is granted)
```
📰 Doornegar — Project Hub
├── 🗺️  Strategy & Vision
│   ├── Mission, positioning, roadmap
│   └── Key decisions log (mirror of DECISION_LOG.md)
├── 📝 Content & Editorial
│   ├── Weekly digests (Niloofar output)
│   ├── Source score tracking
│   └── Content quality audits
├── 🤝 Partnerships & Outreach
│   ├── NGO / academic contacts
│   ├── Media partners
│   └── Grant applications
├── ⚖️  Legal & Compliance
│   ├── IID nonprofit structure
│   ├── Anonymity plan (legal/17_ANONYMITY_PLAN.md)
│   └── Data protection notes
├── 👥 Team & Collaboration
│   ├── Onboarding (mirror of ONBOARDING.md)
│   ├── Task board (database)
│   └── Meeting notes
└── 📊 Metrics & Reports
    ├── Weekly status
    └── Cost tracking
```

## Step 3 — Tell Claude to build it
Once the page exists and is shared with the integration, say: "Build out the Notion project hub structure." Claude will create the child pages, seed starter content from existing markdown files, and populate a task board.
