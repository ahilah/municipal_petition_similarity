# Municipal E-Petition Semantic Similarity & Deduplication System

<p align="center">
  <b>Master's Thesis Project | Lviv Polytechnic National University</b><br>
  Department of Automated Control Systems (Group KNUS-11)<br>
  <b>Author:</b> Anastasiia Hileta
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Streamlit-App-red.svg" alt="Streamlit">
  <img src="https://img.shields.io/badge/PyTorch-Deep%20Learning-orange.svg" alt="PyTorch">
  <img src="https://img.shields.io/badge/spaCy-NLP-green.svg" alt="spaCy">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

---

## Overview

This project is developed as a Master's qualification thesis focusing on the automated detection of semantic similarity between electronic petitions and the identification of duplicate or closely related civic initiatives. 

The system implements a **Two-Stage Retrieval** architecture combining dense semantic vector embeddings (`intfloat/multilingual-e5-small`) with a custom domain-specific rule engine (`DomainContextEngine`) and continuous geospatial distance validation (Haversine formula) to prevent false-positive duplicate flags in municipal governance platforms.

---

## Key Features

- **Semantic Deduplication:** Vector-based similarity search across active municipal petition corpora using PyTorch and Sentence-Transformers.
- **Domain Context Engine:** Advanced Named Entity Recognition (NER) and EntityRuler integration via `spaCy` (`uk_core_news_lg`) to isolate specific entities (schools, routes, streets, quotes) and domain categories (roads, education, ecology, housing).
- **Geospatial Verification:** Automatic coordinate extraction and continuous Haversine distance penalty calculation to filter out geographically distant initiatives.
- **Analytical Dashboard:** Interactive Plotly charts visualizing thematic categories, municipal activity ratings, and temporal activity distributions.
- **Automated Audit Reporting:** Generation of official review protocols and audit reports in CSV and PDF formats (`fpdf2`).

---

## Technology Stack

- **Frontend & UI:** Streamlit, Streamlit-Folium, Plotly
- **NLP & Embeddings:** Sentence-Transformers (`intfloat/multilingual-e5-small`), spaCy (`uk_core_news_lg`)
- **Machine Learning & Core:** PyTorch, Pandas, NumPy, Scikit-learn
- **Geospatial & Mapping:** Folium, OpenStreetMap Nominatim API
- **Reporting:** FPDF2 (PDF generation)

---

## Project Structure

```text
masters-thesis/
│
├── assets/                 # Custom CSS styles and graphical resources
│   └── style.css
│
├── data/                   # Cleaned datasets, serialized embeddings, and caches
│   ├── petitions_cleaned.csv
│   ├── embeddings.pt
│   └── coords_cache.json
│
├── notebooks/              # Experimental scripts and EDA notebooks
│   └── ...
│
├── app.py                  # Main Streamlit web application entry point
├── engine.py               # Domain context engine, NER rules, and entity extraction
├── matcher.py              # Two-stage retrieval and semantic search pipeline
├── geocoding.py            # Geocoding utilities and Haversine distance calculations
├── mapping.py              # Folium map and heatmap generator
├── reports.py              # CSV and PDF audit protocol generator
├── ui_components.py        # HTML/CSS template cards for UI rendering
├── validation.py           # Input text validation logic
└── requirements.txt        # Project dependencies


### Key Features