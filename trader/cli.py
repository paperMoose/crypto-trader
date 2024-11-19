@click.command()
@click.option('--symbol', default='dogeusd', help='Symbol to check P&L for')
def show_pnl(symbol):
    """Show current P&L for a symbol"""
    session = get_session()
    client = GeminiClient()
    pnl_service = PnLService(session, client)
    
    pnl = asyncio.run(pnl_service.update_pnl(symbol))
    
    click.echo(f"\nP&L Report for {symbol.upper()}:")
    click.echo(f"Current Position: {pnl.current_position}")
    click.echo(f"Average Entry: ${pnl.average_entry}")
    click.echo(f"Realized P&L: ${pnl.realized_pl}")
    click.echo(f"Unrealized P&L: ${pnl.unrealized_pl}")
    click.echo(f"Total P&L: ${Decimal(pnl.realized_pl) + Decimal(pnl.unrealized_pl)}")
    click.echo(f"Total Fees: ${pnl.total_fees}")

@click.command()
@click.option('--year', type=int, required=True, help='Tax year to generate report for')
def tax_report(year):
    """Generate tax report for a specific year"""
    session = get_session()
    client = GeminiClient()
    pnl_service = PnLService(session, client)
    
    tax_events = asyncio.run(pnl_service.get_tax_report(year))
    
    click.echo(f"\nTax Report for {year}:")
    total_short_term = Decimal('0')
    total_long_term = Decimal('0')
    
    for event in tax_events:
        gain_loss = Decimal(event['gain_loss'])
        if event['is_long_term']:
            total_long_term += gain_loss
        else:
            total_short_term += gain_loss
            
        click.echo(f"\nTrade: {event['amount']} {event['symbol']}")
        click.echo(f"Bought: {event['acquisition_date']}")
        click.echo(f"Sold: {event['disposal_date']}")
        click.echo(f"Holding Period: {event['holding_period_days']} days")
        click.echo(f"Cost Basis: ${event['cost_basis']}")
        click.echo(f"Sale Proceeds: ${event['sale_proceeds']}")
        click.echo(f"Gain/Loss: ${event['gain_loss']} ({'Long-term' if event['is_long_term'] else 'Short-term'})")
    
    click.echo(f"\nSummary:")
    click.echo(f"Total Short-term Gain/Loss: ${total_short_term}")
    click.echo(f"Total Long-term Gain/Loss: ${total_long_term}")
    click.echo(f"Total Gain/Loss: ${total_short_term + total_long_term}") 