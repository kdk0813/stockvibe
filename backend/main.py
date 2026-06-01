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
        # 전일 종가와 현재가를 가져오기 위해 2일치 데이터 조회
        data = ticker.history(period="2d")
        if data.empty:
            raise HTTPException(status_code=404, detail="Stock not found")
        
        current_price = data['Close'].iloc[-1]
        prev_close = data['Close'].iloc[-2] if len(data) > 1 else current_price
        change = current_price - prev_close
        pct_change = (change / prev_close) * 100 if prev_close != 0 else 0

        return {
            "symbol": symbol.upper(),
            "price": round(current_price, 2),
            "change": round(change, 2),
            "changesPercentage": round(pct_change, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. 관심 종목 전체 조회
@app.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    items = db.query(Watchlist).all()
    results = []
    for item in items:
        try:
            ticker = yf.Ticker(item.symbol)
            data = ticker.history(period="2d")
            if not data.empty:
                current_price = data['Close'].iloc[-1]
                prev_close = data['Close'].iloc[-2] if len(data) > 1 else current_price
                change = current_price - prev_close
                pct_change = (change / prev_close) * 100 if prev_close != 0 else 0
                
                results.append({
                    "symbol": item.symbol,
                    "price": round(current_price, 2),
                    "change": round(change, 2),
                    "changesPercentage": round(pct_change, 2)
                })
            else:
                results.append({"symbol": item.symbol, "price": 0, "change": 0, "changesPercentage": 0})
        except:
            results.append({"symbol": item.symbol, "price": 0, "change": 0, "changesPercentage": 0})
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
