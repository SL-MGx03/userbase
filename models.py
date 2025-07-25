import os
from sqlalchemy import create_engine, Column, BigInteger, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import func

# Get the database URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable not set.")

# SQLAlchemy requires 'postgresql://' instead of 'postgres://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# The Declarative Base is a factory for creating mapped classes
Base = declarative_base()

class TelegramUser(Base):
    """SQLAlchemy model for the telegram_users table."""
    __tablename__ = 'telegram_users'

    telegram_id = Column(BigInteger, primary_key=True, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    is_bot = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<TelegramUser(id={self.telegram_id}, name='{self.first_name}')>"

# Create the database engine
engine = create_engine(DATABASE_URL)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Creates the table in the database if it doesn't exist."""
    print("Initializing database and creating tables if they don't exist...")
    Base.metadata.create_all(bind=engine)
    print("Database initialization complete.")
