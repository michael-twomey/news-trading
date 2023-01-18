import util
from time import sleep

def get_news(session):
    return session.get('http://localhost:9999/v1/news?limit=1').json()

def parse_news(news):
    if news is None:
        return
    
    headline = news['headline']
    first_letter = headline[0]

    # Check if news is an EIA report
    if (first_letter == 'W'):
        # Turn news into a list for easier parsing
        headline = headline.split(" ")
        actual_stock = headline[4]
        actual_qty = headline[5]
        forecast_stock = headline[10]
        forecast_qty = headline[11]
        return {
            'actual_stock': actual_stock,
            'actual_qty': actual_qty,
            'forecast_stock': forecast_stock,
            'forecast_qty': forecast_qty
        }

    return

def interpret_news(news):
    if news is None:
        return 

    actual_stock = news['actual_stock']
    actual_qty = news['actual_qty']
    forecast_stock = news['forecast_stock']
    forecast_qty = news['forecast_qty']
    actual_qty = int(actual_qty)
    forecast_qty = int(forecast_qty)

    # Build build
    if ((actual_stock == 'BUILD') and (forecast_stock == 'BUILD')):
        dif = actual_qty - forecast_qty
        # Divide by 10 becasue value of CL will adjust by $1 per 10 million barrels
        price_shock = dif / 10
        # Multiply price shock times 100 contracts times 1000 barrels per contract for max potential profit
        potential_profit = round(price_shock * 100 * 1_000 * -1)
        print('price-shock: ' + str(price_shock))
        print('potential-profit: ' + str(potential_profit))
        print('build-build-dif: ' + str(dif))
        if (actual_qty > forecast_qty):
            return { 'trade_decision': 'SELL', 'price_shock': price_shock }
        elif (actual_qty == forecast_qty):
            return { 'trade_decision': 'EQUAL', 'price_shock': price_shock }
        else:
            return { 'trade_decision': 'BUY', 'price_shock': price_shock }

    # Draw build
    elif ((actual_stock == 'DRAW') and (forecast_stock == 'BUILD')):
        dif = (actual_qty * -1) - forecast_qty
        price_shock = dif / 10
        potential_profit = round(price_shock * 100 * 1000 * -1)
        print('price-shock: ' + str(price_shock))
        print('potential-profit: ' + str(potential_profit))
        print('draw-build-dif: ' + str(dif))
        return { 'trade_decision': 'BUY', 'price_shock': price_shock * -1 }
    
    # Build draw
    elif ((actual_stock == 'BUILD') and (forecast_stock == 'DRAW')):
        dif = actual_qty - (forecast_qty * -1)
        price_shock = dif / 10
        potential_profit = round(price_shock * 100 * 1000 * -1)
        print('price-shock: ' + str(price_shock))
        print('potential-profit: ' + str(potential_profit))
        print('build-draw-dif: ' + str(dif))
        return { 'trade_decision': 'SELL', 'price_shock': price_shock }

    # Draw draw
    else:
        dif = actual_qty - forecast_qty
        price_shock = dif / 10
        potential_profit = round(price_shock * 100 * 1000)
        print('price-shock: ' + str(price_shock))
        print('potential-profit: ' + str(potential_profit))
        print('draw-draw-dif: ' + str(dif))        
        if (actual_qty > forecast_qty):
            return { 'trade_decision': 'BUY', 'price_shock': price_shock }
        elif (actual_qty == forecast_qty):
            return { 'trade_decision': 'EQUAL', 'price_shock': price_shock }
        else:
            return { 'trade_decision': 'SELL', 'price_shock': price_shock }

def place_order(session, ticker, qty, trade_decision):
    storage_ticker = 'CL-STORAGE'
    orders_placed = 0
    orders = 7

    # Price shock from news needs to be greater than or equal to $0.50 for it to be worthwhile to act
    if (trade_decision is None or abs(trade_decision['price_shock']) < 0.5):
        trade_decision = None
        return trade_decision
    
    # orders_placed set to place x orders of 10 contracts to complement refining positon
    while trade_decision['trade_decision'] == 'BUY' and orders_placed < orders:
        util.lease_storage(session, storage_ticker)
        sleep(0.5)
        util.place_mkt_buy_order(session, ticker, qty)
        orders_placed += 1

    while trade_decision['trade_decision'] == 'SELL' and orders_placed < orders:
        futures_ticker = util.get_futures_ticker(session)
        util.place_mkt_sell_order(session, futures_ticker, qty)
        orders_placed += 1
        sleep(0.5)

    return trade_decision

def reset_position(session, trade_decision):
    if (trade_decision is None):
        return

    orders_placed = 0
    orders = 7

    if (trade_decision['trade_decision'] == 'BUY'):
        ticker = 'CL'
        quantity = 10
        price_shock = trade_decision['price_shock']
        print('price_shock: ' + str(price_shock))
        spot = session.get(f'http://localhost:9999/v1/securities?ticker={ticker}').json()[0]
        spot_price = spot['last']
        old_spot_price = spot_price
        
        # While current price has increased by less than 75% of expected price shock:
        while spot_price < ((old_spot_price + (price_shock * 0.75))):
            updated_spot = session.get(f'http://localhost:9999/v1/securities?ticker={ticker}').json()[0]
            sleep(0.5)
            spot_price = updated_spot['last']
            spot_price_plus_shock = (old_spot_price + (price_shock * 0.7))
            print('spot-price: ' + str(spot_price))
            print('spot-price-plus-shock: ' + str(spot_price_plus_shock))
            # When the current price has factored in more than 70% of the price shock and less than 75% of the price shock,
            # unload the positon
            if (spot_price >= (old_spot_price + (price_shock * 0.7))):
                while orders_placed < orders:
                    util.place_mkt_sell_order(session, ticker, quantity)
                    sleep(0.5)
                    util.cancel_leases(session)
                    orders_placed += 1
                    sleep(0.5)

    elif (trade_decision['trade_decision'] == 'SELL'):
        quantity = 10
        price_shock = trade_decision['price_shock']
        futures_ticker = util.get_futures_ticker(session)
        futures = session.get(f'http://localhost:9999/v1/securities?ticker={futures_ticker}').json()[0]
        futures_price = futures['last']
        old_futures_price = futures_price
        
        # While current price has decreased by less than 75% of expected price shock:
        while futures_price > (old_futures_price - (price_shock * 0.75)):
            updated_futures = session.get(f'http://localhost:9999/v1/securities?ticker={futures_ticker}').json()[0]
            sleep(0.5)
            futures_price = updated_futures['last']
            futures_price_minus_shock = (old_futures_price - (price_shock * 0.7))
            print('futres-price: ' + str(futures_price))
            print('futures-price-minus-shock: ' + str(futures_price_minus_shock))
            # When the current price has factored in more than 70% of the price shock and less than 75% of the price shock,
            # reset the positon
            if (futures_price <= (old_futures_price - (price_shock * 0.7))):
                while orders_placed < orders:
                    util.place_mkt_buy_order(session, futures_ticker, quantity)
                    orders_placed += 1
                    sleep(0.5)
    
def main():
    session = util.open_session()
    tick = util.get_tick(session)
    ticker = 'CL'
    quantity = 10
    old_news_id = -1

    while tick >= 0 and tick <= 600:
        news = get_news(session)[0]

        # Wrapped in if statement to handle no news reports at start of simulation
        if news['headline'] != 'Welcome to the Commodities Trading 5 Case':
            # Prevents algo from interpreting old news as new news
            if (news['news_id'] == old_news_id):
                news = None
            news_results = parse_news(news)
            trade_decision = interpret_news(news_results)
            print(trade_decision)
            trade_decision = place_order(session, ticker, quantity, trade_decision)
            sleep(1)
            reset_position(session, trade_decision)
            # Set news that was just used to old_news_id to prevent it from being used again
            if news is not None:
                old_news_id = news['news_id']
        
        tick = util.get_tick(session)
        print('tick: ' + str(tick))

main()
