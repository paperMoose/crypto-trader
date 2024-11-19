import click
from sqlmodel import Session, create_engine
from trader.services import StrategyService
from trader.gemini.client import GeminiClient
from tabulate import tabulate
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment or use default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///orders.db")

def get_session():
    engine = create_engine(DATABASE_URL)
    return Session(engine)

def get_strategy_service():
    session = get_session()
    client = GeminiClient()  # We won't use this for PnL queries
    return StrategyService(client, session)

@click.group()
def cli():
    """Trading bot CLI commands"""
    pass

@cli.command()
def summary():
    """Show total profit/loss summary across all strategies"""
    service = get_strategy_service()
    
    try:
        results = service.get_total_profits_summary()
        
        # Format data for table
        table_data = [
            ["Total Profit", f"${results['total_profit']}"],
            ["Realized Profit", f"${results['total_realized']}"],
            ["Tax Reserve", f"${results['tax_reserve']}"],
            ["Available Profit", f"${results['available_profit']}"]
        ]
        
        # Print table
        print("\nProfit/Loss Summary")
        print("==================")
        print(tabulate(table_data, tablefmt="simple"))
        
    except Exception as e:
        click.echo(f"Error getting summary: {str(e)}", err=True)

@cli.command()
def details():
    """Show detailed profit/loss breakdown by strategy"""
    service = get_strategy_service()
    
    try:
        results = service.get_profits_by_strategy()
        
        if not results:
            click.echo("No strategies found")
            return
            
        # Format data for table
        table_data = []
        headers = ["Strategy", "Symbol", "Type", "Total P/L", "Realized", "Tax Reserve", "Available"]
        
        for result in results:
            table_data.append([
                result['strategy_name'],
                result['symbol'],
                result['type'].value,
                f"${result['total_profit']}",
                f"${result['realized_profit']}",
                f"${result['tax_reserve']}",
                f"${result['available_profit']}"
            ])
        
        # Print table
        print("\nStrategy Profit/Loss Details")
        print("===========================")
        print(tabulate(table_data, headers=headers, tablefmt="simple"))
        
    except Exception as e:
        click.echo(f"Error getting details: {str(e)}", err=True)

if __name__ == "__main__":
    cli() 