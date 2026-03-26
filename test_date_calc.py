import datetime

def test_calc(data_vencimento_str):
    try:
        if '-' in data_vencimento_str:
            venc = datetime.datetime.strptime(data_vencimento_str.split(' ')[0], "%Y-%m-%d").date()
        elif '/' in data_vencimento_str:
            venc = datetime.datetime.strptime(data_vencimento_str.split(' ')[0], "%d/%m/%Y").date()
        else:
            venc = datetime.date.today()
    except Exception as e:
        print(f"Error: {e}")
        venc = datetime.date.today()
        
    hoje = datetime.date.today()
    dias_atraso = (hoje - venc).days
    print(f"Data Vencimento: {data_vencimento_str} -> {venc}")
    print(f"Hoje: {hoje}")
    print(f"Dias Atraso: {dias_atraso}")

test_calc("04/02/2026")
test_calc("2026-02-04")
