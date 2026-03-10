from pathlib import Path

# =========================
# 1. 폴더 구조 정의
# =========================
DIRS = [
    "configs",
    "data/raw/market",
    "data/raw/stock",
    "data/raw/etf",
    "data/processed/market",
    "data/processed/stock",
    "data/processed/etf",
    "data/outputs/predictions",
    "data/outputs/reports",
    "models/market",
    "models/stock",
    "models/etf",
    "universe",
    "scripts/00_fetch",
    "scripts/01_features",
    "scripts/02_train",
    "scripts/03_predict",
    "scripts/99_utils",
    "src/common",
    "src/market",
    "src/stock",
    "src/etf",
    "agents/tools",
    "agents/prompts",
    "tests"
]

# =========================
# 2. 기본 파일 템플릿
# =========================

FILES = {
    "README.md": "# Stock & ETF Short-Term Direction Model\n",
    ".gitignore": "data/\n.env\n__pycache__/\n*.pyc\n",
    "requirements.txt": """pandas
numpy
pyarrow
pyyaml
scikit-learn
lightgbm
tqdm
crewai
crewai-tools
python-dotenv
""",
    "configs/base.yaml": """paths:
  data_dir: "data"
  models_dir: "models"
  outputs_dir: "data/outputs"

run:
  horizons: [5, 10]
  seed: 42

label:
  market_neutral_th: 0.01
  stock_excess: true

features:
  lookbacks: [1,2,3,5,10,20]
""",
    "configs/market.yaml": "model:\n  objective: multiclass\n  num_class: 3\n",
    "configs/stock.yaml": "model:\n  objective: binary\n",
    "configs/etf.yaml": "model:\n  objective: binary\n",
    "src/__init__.py": "",
    "src/common/__init__.py": "",
    "src/market/__init__.py": "",
    "src/stock/__init__.py": "",
    "src/etf/__init__.py": "",
    "agents/__init__.py": "",
    "agents/tools/__init__.py": "",
}

# =========================
# 3. 생성 로직
# =========================

def create_structure():
    print("📁 Creating directories...")
    for d in DIRS:
        path = Path(d)
        path.mkdir(parents=True, exist_ok=True)
        print(f"  ✔ {path}")

    print("\n📄 Creating template files...")
    for filepath, content in FILES.items():
        path = Path(filepath)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            print(f"  ✔ {path}")
        else:
            print(f"  - Skipped (exists): {path}")

    print("\n✅ Project structure initialized successfully!")


if __name__ == "__main__":
    create_structure()