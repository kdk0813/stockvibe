from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import yfinance as yf

# --- 데이터베이스 설정 ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./stockvibe.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Watchlist(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FastAPI 앱 설정 ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to StockVibe API"}

# 1. 특정 종목 가격 조회
@app.get("/stock/{symbol}")
def get_stock_price(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if data.empty:
            raise HTTPException(status_code=404, detail="Stock not found")
        return {"symbol": symbol.upper(), "price": round(data['Close'].iloc[-1], 2)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. 관심 종목 전체 조회
@app.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    items = db.query(Watchlist).all()
    results = []
    for item in items:
        # 각 종목의 현재가도 함께 가져옴
        ticker = yf.Ticker(item.symbol)
        data = ticker.history(period="1d")
        price = round(data['Close'].iloc[-1], 2) if not data.empty else 0
        results.append({"symbol": item.symbol, "price": price})
    return results

# 3. 관심 종목 추가
@app.post("/watchlist/{symbol}")
def add_to_watchlist(symbol: str, db: Session = Depends(get_db)):
    db_item = db.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
    if db_item:
        return {"message": "Already in watchlist"}
    
    new_item = Watchlist(symbol=symbol.upper())
    db.add(new_item)
    db.commit()
    return {"message": f"Added {symbol} to watchlist"}

# 4. 관심 종목 삭제
@app.delete("/watchlist/{symbol}")
def remove_from_watchlist(symbol: str, db: Session = Depends(get_db)):
    db_item = db.query(Watchlist).filter(Watchlist.symbol == symbol.upper()).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Not found in watchlist")
    
    db.delete(db_item)
    db.commit()
    return {"message": f"Removed {symbol} from watchlist"}
