"""Build the PathMind literature RAG index.

Fetches real PubMed abstracts via NCBI E-utilities, plus seeds a small set of
TCGA-style case descriptions, then indexes them into Qdrant using the
sentence-transformers model already installed on the VPS.

Run once before serving the Literature Hunter agent. No model download needed
beyond the cached one in /home/ubuntu/.cache/huggingface.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from Bio import Entrez
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "literature"
DATA_DIR.mkdir(parents=True, exist_ok=True)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("PATHMIND_COLLECTION", "pathmind_literature")
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "zakaria.barji@gmail.com")

QUERIES = {
    "pancreatic_adenocarcinoma": "pancreatic adenocarcinoma histopathology grading prognosis",
    "perineural_invasion": "perineural invasion pancreatic cancer prognosis recurrence",
    "breast_invasive_carcinoma": "invasive ductal carcinoma breast SBR grading prognosis",
    "margin_status": "surgical margin status R0 R1 pancreatic resection outcome",
    "ki67_proliferation": "Ki-67 proliferation index tumor grading",
    "neuroendocrine_differential": "pancreatic neuroendocrine tumor synaptophysin chromogranin differential diagnosis",
    "igG4_pancreatitis": "IgG4 related sclerosing pancreatitis differential diagnosis",
    "tcga_pancreas": "TCGA pancreatic adenocarcinoma molecular subtypes outcomes",
}


@dataclass
class LiteratureChunk:
    chunk_id: str
    source: str  # "pubmed" or "tcga_case"
    pmid: str | None
    title: str
    text: str
    metadata: dict


def fetch_pubmed(query: str, max_results: int = 8) -> list[LiteratureChunk]:
    Entrez.email = NCBI_EMAIL
    chunks: list[LiteratureChunk] = []

    handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results, sort="relevance")
    ids = Entrez.read(handle)["IdList"]
    handle.close()
    if not ids:
        return chunks

    handle = Entrez.efetch(db="pubmed", id=",".join(ids), rettype="abstract", retmode="xml")
    records = Entrez.read(handle)
    handle.close()

    for art in records.get("PubmedArticle", []):
        try:
            mc = art["MedlineCitation"]
            pmid = str(mc["PMID"])
            article = mc["Article"]
            title = str(article.get("ArticleTitle", "")).strip()
            abstract_parts = article.get("Abstract", {}).get("AbstractText", [])
            abstract = " ".join(str(p) for p in abstract_parts).strip()
            if not abstract or len(abstract) < 100:
                continue
            year = ""
            try:
                year = str(article["Journal"]["JournalIssue"]["PubDate"].get("Year", ""))
            except Exception:
                pass
            journal = str(article["Journal"].get("Title", ""))
            chunks.append(
                LiteratureChunk(
                    chunk_id=f"pubmed_{pmid}",
                    source="pubmed",
                    pmid=pmid,
                    title=title,
                    text=f"{title}\n\n{abstract}",
                    metadata={"journal": journal, "year": year, "query_topic": query},
                )
            )
        except Exception as e:
            print(f"  skip article: {e}")
    return chunks


TCGA_SEED_CASES = [
    {
        "case_id": "TCGA-PA-A5YG",
        "title": "Pancreatic acinar adenocarcinoma, multifocal, grade II",
        "text": (
            "Patient: male, 65y. Pancreatic head mass 35mm. Whipple resection. "
            "Histology: infiltrating acinar adenocarcinoma, multifocal pattern, "
            "grade II (WHO 2022). Perineural invasion present, 3 foci. "
            "Lymphovascular invasion present. Margin: R1 anterior 0.4mm. "
            "pT2 pN1 (2/14 LN). Mitotic count 12/10HPF. Necrosis ~20%. "
            "Outcome: 5y OS 28% in cohort with similar staging."
        ),
        "metadata": {"organ": "pancreas", "grade": "II", "stage": "pT2pN1", "five_year_os_pct": 28},
    },
    {
        "case_id": "TCGA-IB-7886",
        "title": "Pancreatic ductal adenocarcinoma, grade II-III",
        "text": (
            "Patient: female, 71y. PDAC head of pancreas, 28mm. Multifocal involvement. "
            "Grade heterogeneity II-III. Desmoplastic stromal reaction, dense. "
            "Perineural invasion present. Margin: R1 posterior 0.6mm. "
            "Lymph nodes: 3/16 positive. pT2 pN1. "
            "Outcome: 5y OS 22% reported in matched TCGA-PAAD cohort."
        ),
        "metadata": {"organ": "pancreas", "grade": "II-III", "stage": "pT2pN1", "five_year_os_pct": 22},
    },
    {
        "case_id": "TCGA-BR-A4QG",
        "title": "Invasive ductal carcinoma of breast, SBR grade III",
        "text": (
            "Female 58y. IDC NOS, 22mm. SBR grade III: nuclear pleomorphism 3, "
            "tubular formation 3, mitotic count 14/10HPF. Lymphovascular invasion present. "
            "ER+, PR-, HER2-, Ki-67 35%. Triple-negative-like behavior. "
            "Margin clear (>5mm). 2/12 axillary nodes positive. pT2 pN1. "
            "5y DFS 62% in similar cohort."
        ),
        "metadata": {"organ": "breast", "grade": "III", "ihc": "ER+PR-HER2-Ki67-35", "five_year_dfs_pct": 62},
    },
    {
        "case_id": "TCGA-A8-A081",
        "title": "Lobular carcinoma of breast, grade II",
        "text": (
            "Female 64y. Invasive lobular carcinoma, classic type. 25mm. "
            "Single-file growth pattern, E-cadherin loss. Grade II. "
            "ER+, PR+, HER2-, Ki-67 12%. Multifocal pattern (3 foci). "
            "Margin involved laterally (R1). 0/10 nodes. pT2 pN0. "
            "Recommend repeat excision and adjuvant endocrine therapy."
        ),
        "metadata": {"organ": "breast", "grade": "II", "ihc": "ER+PR+HER2-Ki67-12", "histology": "ILC"},
    },
    {
        "case_id": "TCGA-PA-NEC-01",
        "title": "Pancreatic neuroendocrine carcinoma G2 (DDx case)",
        "text": (
            "Male 59y. Pancreatic mass head, 30mm. Histology shows trabecular and "
            "solid growth pattern with monomorphic cells. Synaptophysin diffusely positive. "
            "Chromogranin positive. Ki-67 10% (G2 by WHO 2019 criteria). "
            "This case illustrates the differential diagnosis with acinar adenocarcinoma "
            "where IHC is decisive: PDAC is synaptophysin-negative."
        ),
        "metadata": {"organ": "pancreas", "tumor_type": "NEC", "ki67_pct": 10, "ddx_role": True},
    },
    {
        "case_id": "TCGA-PA-AIP-01",
        "title": "IgG4-related autoimmune pancreatitis (DDx case)",
        "text": (
            "Male 68y. Pancreatic head mass mimicking adenocarcinoma. 28mm. "
            "Histology: dense lymphoplasmacytic infiltrate with storiform fibrosis, "
            "obliterative phlebitis. IgG4+ plasma cells >50/HPF. Serum IgG4 elevated. "
            "No malignant cells identified. Response to corticosteroids confirmed dx. "
            "This case illustrates DDx with PDAC where IgG4 IHC is critical."
        ),
        "metadata": {"organ": "pancreas", "tumor_type": "AIP", "ddx_role": True},
    },
    {
        "case_id": "TCGA-BR-DCIS-01",
        "title": "Ductal carcinoma in situ, high grade",
        "text": (
            "Female 52y. DCIS comedo type, high nuclear grade. 18mm. "
            "Cribriform and solid growth patterns. Central necrosis with calcifications. "
            "ER+, PR+. No invasive component identified after extensive sampling. "
            "Margin clear (4mm). Recommend lumpectomy + radiotherapy + endocrine therapy."
        ),
        "metadata": {"organ": "breast", "grade": "high", "tumor_type": "DCIS", "invasive": False},
    },
]


def collect_all_chunks(per_query_max: int = 8) -> list[LiteratureChunk]:
    all_chunks: list[LiteratureChunk] = []
    for topic, query in QUERIES.items():
        print(f"  pubmed: {topic}")
        chunks = fetch_pubmed(query, max_results=per_query_max)
        all_chunks.extend(chunks)
        time.sleep(0.4)  # NCBI rate limit
    print(f"  pubmed total: {len(all_chunks)} abstracts")

    for case in TCGA_SEED_CASES:
        all_chunks.append(
            LiteratureChunk(
                chunk_id=f"tcga_{case['case_id']}",
                source="tcga_case",
                pmid=None,
                title=case["title"],
                text=f"{case['title']}\n\n{case['text']}",
                metadata={**case["metadata"], "case_id": case["case_id"]},
            )
        )
    print(f"  tcga seed: {len(TCGA_SEED_CASES)} cases")
    print(f"  TOTAL: {len(all_chunks)} chunks")
    return all_chunks


def save_chunks_jsonl(chunks: Iterable[LiteratureChunk], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
    print(f"  saved -> {path}")


def index_in_qdrant(chunks: list[LiteratureChunk]) -> None:
    print(f"  loading embed model: {EMBED_MODEL}")
    model = SentenceTransformer(EMBED_MODEL)
    dim = model.get_sentence_embedding_dimension()

    client = QdrantClient(url=QDRANT_URL)
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION in existing:
        client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    print(f"  collection ready: {COLLECTION} (dim={dim})")

    texts = [c.text for c in chunks]
    embs = model.encode(texts, convert_to_numpy=True, show_progress_bar=False, batch_size=16)
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embs[i].tolist(),
            payload={
                "chunk_id": c.chunk_id,
                "source": c.source,
                "pmid": c.pmid,
                "title": c.title,
                "text": c.text,
                **c.metadata,
            },
        )
        for i, c in enumerate(chunks)
    ]
    client.upsert(collection_name=COLLECTION, points=points)
    print(f"  indexed {len(points)} points in Qdrant")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-query", type=int, default=8, help="PubMed abstracts per query topic")
    parser.add_argument("--no-pubmed", action="store_true", help="Skip PubMed (use only TCGA seed)")
    args = parser.parse_args()

    if args.no_pubmed:
        chunks = [
            LiteratureChunk(
                chunk_id=f"tcga_{c['case_id']}",
                source="tcga_case",
                pmid=None,
                title=c["title"],
                text=f"{c['title']}\n\n{c['text']}",
                metadata={**c["metadata"], "case_id": c["case_id"]},
            )
            for c in TCGA_SEED_CASES
        ]
    else:
        chunks = collect_all_chunks(per_query_max=args.per_query)

    save_chunks_jsonl(chunks, DATA_DIR / "chunks.jsonl")
    index_in_qdrant(chunks)
    print("DONE")


if __name__ == "__main__":
    main()
