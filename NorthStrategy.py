import pandas as pd
import numpy as np
from datetime import datetime
from pyecharts import options as opts
from pyecharts.charts import Line, Bar
import tushare as ts
ts.set_token('34dc0a4096580b9684445be79001171498e568a3e446e310d63aa418')

pro = ts.pro_api()

def NorthStrategy(data,window,stdev_n,cost,start_date='20170101',end_date='29990101'):
    '''
    :param data: 包括北向资金和指数价格数据
    :param window: 移动窗口
    :param stdev_n: 几倍标准差
    :param cost: 手续费
    :param start_date:
    :param end_date:
    :return:
    '''
    # mid
    df=data.copy().dropna()
    df['mid']=df['北向资金'].rolling(window).mean()
    stdev=df['北向资金'].rolling(window).std()
    #up,low
    df['upper'] = df['mid'] + stdev_n * stdev
    df['lower'] = df['mid'] - stdev_n * stdev
    df['ret']=df.close/df.close.shift(1)-1

    df.dropna(inplace=True)
    df=df.loc[(df.trade_date>=start_date) & (df.trade_date<=end_date)]

    #TradeStrategy
    #北上资金突破上轨为买入信号.
    df.loc[df['北向资金']>df.upper, 'signal'] = 1
    # 北上资金跌破下轨为卖出信号
    df.loc[df['北向资金']<df.lower, 'signal'] = 0
    df['position']=df['signal'].shift(1)
    df['position'].fillna(method='ffill',inplace=True)
    df['position'].fillna(0, inplace=True)
    #print(df)
    # df['capital_ret'] = df['position'].shift(1)
    # df['capital_ret'].fillna(method='ffill', inplace=True)
    # df['capital_ret'].fillna(0, inplace=True)
    #根据交易信号和仓位计算策略的每日收益率
    df.loc[df.index[0], 'capital_ret']=0
    df.loc[df.index[0], 'capital_ret_without_fee'] = 0
    #今天开盘买入的position在今天的涨幅（扣除手续费）
    df.loc[df['position'] > df['position'].shift(1), 'capital_ret']=df.close/(df.open*(1+cost))-1
    df.loc[df['position'] > df['position'].shift(1), 'capital_ret_without_fee'] = df.close / df.open  - 1
    #卖出
    df.loc[df['position'] < df['position'].shift(1), 'capital_ret'] = df.close / (df.open * (1 - cost)) - 1
    df.loc[df['position'] < df['position'].shift(1), 'capital_ret_without_fee'] = df.close / df.open - 1
    #仓位不变时，当天的capital是当天的chage*position
    df.loc[df['position'] == df['position'].shift(1), 'capital_ret'] = df['ret']*df['position']
    df.loc[df['position'] == df['position'].shift(1), 'capital_ret_without_fee'] = df['ret']*df['position']
    #计算标的、策略、指数的累计收益率
    df['策略净值']=[round(x,2) for x in (df.capital_ret+1.0).cumprod()]
    df['策略净值(无手续费)'] = [round(x, 2) for x in (df.capital_ret_without_fee + 1.0).cumprod()]
    df['指数净值']=[round(x,2) for x in (df.ret+1.0).cumprod()]

    return df

def performance(ret,benchmark, rf=0.04):
    #计算评价指标
    import empyrical
    max_drawdown = empyrical.max_drawdown(ret)
    total_return =empyrical.cum_returns_final(ret)
    annual_return= empyrical.annual_return(ret)

    sharpe_ratio =empyrical.sharpe_ratio(ret,risk_free=((1+rf)**(1/252)-1))
    alpha,beta=empyrical.alpha_beta(ret,benchmark)
    return {'total_return':total_return,
            'annual_return':annual_return,
            'max_drawdown':max_drawdown,
            'sharpe_ratio':sharpe_ratio,
            'alpha':alpha,
            'beta':beta}
def plot_result(df,index_name):
    line=(
        Line()
            .add_xaxis([str(x) for x in df.trade_date.values])
            .add_yaxis('仓位',df.position.values.tolist(),
                       is_symbol_show=False,
                       is_selected=False,
                       color='red')
            .add_yaxis('PE_TTM',df.pe_ttm.values.tolist(),
                       is_symbol_show=False,
                       is_selected=False,
                       yaxis_index=2,
                       color='blue',
                       linestyle_opts=opts.LineStyleOpts(width=2))
            .extend_axis(yaxis=opts.AxisOpts(type_="value", position="left",))
            .extend_axis(yaxis=opts.AxisOpts(type_="value", position="right",))
            .set_global_opts(datazoom_opts=opts.DataZoomOpts(range_start=0,range_end=100),
                             toolbox_opts=opts.TooltipOpts(trigger='axis'))
    )
    line1=(
        Line()
            .add_xaxis([str(x) for x in df.trade_date.values])
            .add_yaxis('策略净值',df['策略净值'].values.tolist(),
                       yaxis_index=1,
                       color='green',
                       is_symbol_show=False,
                       is_smooth=True,
                       linestyle_opts=opts.LineStyleOpts(width=2)
                       )
            .add_yaxis(index_name,df['指数净值'].values.tolist(),
                       yaxis_index=1,
                       color='red',
                       is_symbol_show=False,
                       is_smooth=True,
                       linestyle_opts=opts.LineStyleOpts(width=2)
                       )
            .add_yaxis('策略净值(无手续费)', df['策略净值(无手续费)'].values.tolist(),
                       yaxis_index=1,
                       color='black',
                       is_symbol_show=False,
                       is_smooth=True,
                       )
    )
    line.overlap(line1)
    return line

def get_data(index_code='000300.SH'):
    data = pd.read_csv("north_data.csv")
    data.rename(columns={'north_money':'北向资金'},inplace=True)
    data['trade_date']=[str(x) for x in data['trade_date'].values]

    index_data = pro.index_daily(ts_code=index_code)[['trade_date','open','close']]
    index_data = pd.merge(index_data, pro.index_dailybasic(ts_code=index_code)[['trade_date','pe_ttm']],
                           how='inner', on='trade_date')
    data = pd.merge(data,index_data,how='inner',on='trade_date')

    return data

def main(window,stdev_n,cost,start_date,end_date,index_code='000300.SH',index_name='沪深300'):
    data =get_data(index_code)
    df=NorthStrategy(data,window,stdev_n,cost,start_date,end_date)
    p1=performance(df.ret,df.ret)
    p2=performance(df.capital_ret,df.ret)
    p3 = performance(df.capital_ret_without_fee, df.ret)
    print(f"回测标的: {index_name}({index_code})")
    print(f"回测区间: {start_date}-{end_date}")
    print(f"总收益率（策略）： {round(p2['total_return']*100,2)}%")
    print(f"年化收益率（策略）： {round(p2['annual_return'] * 100, 2)}%")
    print(f"最大回撤（策略）： {round(p2['max_drawdown'] * 100, 2)}%")
    print(f"夏普比率（策略）： {round(p2['sharpe_ratio'], 2)}%")
    print(f"Alpha（策略）： {round(p2['alpha'], 2)}%")
    print(f"Beta（策略）： {round(p2['beta'], 2)}%")
    return plot_result(df,index_name),df

window=252
stdev_n=1.5
cost=0.6/10000
start_date='20200101'
end_date='20201231'
index_code='000300.SH'
index_name='沪深300'
result,df=main(window,stdev_n,cost,start_date,end_date,index_code,index_name)
result.render_notebook()
