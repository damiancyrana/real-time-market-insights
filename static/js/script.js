// script.js
document.addEventListener("DOMContentLoaded", function() {
    var ws = new WebSocket("ws://" + window.location.host + "/ws");
    ws.onmessage = function(event) {
        var data = JSON.parse(event.data);
        console.log('Otrzymane dane:', data);
        if (data.type === 'order_book') {
            updateOrderBook(data);
            updateVolumeProfile(data);
            updateMarketMetrics(data);
            updateTransactions(data);
            updateDepthChart(data);
            updateCVDChart(data);
            updateRecommendation(data);
            updateFearGreedIndex(data);
            updateOrderImbalance(data);
            updateMomentum(data);
            updateTrendDirection(data);
            updateTrendStrength(data);
            updateSupportResistanceLevels(data);
            updateTickChart(data);
            updateOrderFlow(data);
            updateMarketSentiment(data);
            updateRecentTradeStats(data);
            updateSpread(data); 
        }
    };
    ws.onerror = function(event) {
        console.error("WebSocket error observed:", event);
    };

    var volumeProfileChart = null;
    var depthChart = null;
    var cvdChart = null;
    var tickChart = null;
    var transactionVolumeChart = null;
    var heatmapChart = null; 

    function updateOrderBook(data) {
        try {
            var symbol = data.symbol;
            var orderBook = data.order_book;
            var bidsContainer = document.getElementById("bids");
            var asksContainer = document.getElementById("asks");

            bidsContainer.innerHTML = "";
            asksContainer.innerHTML = "";

            var levels = Object.keys(orderBook).map(Number).sort(function(a, b) {
                return a - b;
            });

            levels.forEach(function(level) {
                var levelData = orderBook[level];
                if (!levelData) return;

                var bid = levelData.bid;
                var bidVolume = levelData.bidVolume;
                var ask = levelData.ask;
                var askVolume = levelData.askVolume;
                var levelNumber = levelData.level;

                // Ustalanie wielkości czcionki na podstawie wolumenu
                var bidFontSize = Math.min(12 + bidVolume / 100, 20);
                var askFontSize = Math.min(12 + askVolume / 100, 20);

                var bidRow = document.createElement("div");
                bidRow.className = "row bid-row";
                bidRow.style.fontSize = bidFontSize + "px";
                bidRow.innerHTML = `
                    <div class="level">L${levelNumber}</div>
                    <div class="price">${bid.toFixed(2)}</div>
                    <div class="volume" style="width: ${Math.min(bidVolume * 2, 200)}px;">${bidVolume}</div>
                `;
                bidsContainer.appendChild(bidRow);

                var askRow = document.createElement("div");
                askRow.className = "row ask-row";
                askRow.style.fontSize = askFontSize + "px";
                askRow.innerHTML = `
                    <div class="level">L${levelNumber}</div>
                    <div class="price">${ask.toFixed(2)}</div>
                    <div class="volume" style="width: ${Math.min(askVolume * 2, 200)}px;">${askVolume}</div>
                `;
                asksContainer.appendChild(askRow);
            });

            // Aktualizacja spreadu
            var bidPrices = levels.map(level => orderBook[level].bid);
            var askPrices = levels.map(level => orderBook[level].ask);

            var bestBid = Math.max(...bidPrices);
            var bestAsk = Math.min(...askPrices);
            var spread = bestAsk - bestBid;
            document.getElementById("spread").innerText = spread.toFixed(2);
        } catch (error) {
            console.error('Błąd w updateOrderBook:', error);
        }
    }

    function updateSpread(data) {
        try {
            var spreadRaw = data.best_spread_raw;
            var spreadTable = data.best_spread_table;

            if (spreadRaw !== null && spreadTable !== null) {
                document.getElementById('spreadRaw').innerText = spreadRaw.toFixed(5);
                document.getElementById('spreadTable').innerText = spreadTable.toFixed(5);
            } else {
                document.getElementById('spreadRaw').innerText = '-';
                document.getElementById('spreadTable').innerText = '-';
            }
        } catch (error) {
            console.error('Błąd w updateSpread:', error);
        }
    }

    function updateVolumeProfile(data) {
        try {
            var volumeProfile = data.volume_profile;
            var ctx = document.getElementById('volumeProfileChart').getContext('2d');

            var prices = Object.keys(volumeProfile).map(price => parseFloat(price));
            var volumes = Object.values(volumeProfile);

            // Sortowanie danych po cenie
            var combined = prices.map((price, index) => {
                return {price: price, volume: volumes[index]};
            }).sort((a, b) => a.price - b.price);

            prices = combined.map(item => item.price);
            volumes = combined.map(item => item.volume);

            if (volumeProfileChart) {
                volumeProfileChart.data.labels = prices;
                volumeProfileChart.data.datasets[0].data = volumes;
                volumeProfileChart.update();
            } else {
                volumeProfileChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: prices,
                        datasets: [{
                            label: 'Profil wolumenu',
                            data: volumes,
                            backgroundColor: function(context) {
                                var index = context.dataIndex;
                                var value = context.dataset.data[index];
                                var maxVolume = Math.max(...volumes);
                                var ratio = value / maxVolume;
                                return `rgba(255, ${Math.floor(255 * (1 - ratio))}, 0, 0.6)`;
                            },
                            borderColor: 'rgba(54, 162, 235, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Cena'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Wolumen'
                                }
                            }
                        }
                    }
                });
            }
        } catch (error) {
            console.error('Błąd w updateVolumeProfile:', error);
        }
    }

    function updateMarketMetrics(data) {
        try {
            var metrics = data.market_metrics;
            document.getElementById('totalVolume').innerText = metrics.total_volume.toFixed(2);
            document.getElementById('averageVolume').innerText = metrics.average_volume.toFixed(2);
            document.getElementById('tradeCount').innerText = metrics.trade_count;
            document.getElementById('orderImbalance').innerText = (data.order_imbalance * 100).toFixed(2) + '%';

            // Nowe statystyki
            document.getElementById('recentAvgVolume').innerText = metrics.recent_avg_volume.toFixed(2);
            document.getElementById('recentAvgPrice').innerText = metrics.recent_avg_price.toFixed(2);
            document.getElementById('recentMaxVolume').innerText = metrics.recent_max_volume.toFixed(2);
            document.getElementById('recentMinVolume').innerText = metrics.recent_min_volume.toFixed(2);

            // Dzienne High i Low
            document.getElementById('dailyHigh').innerText = metrics.high.toFixed(2);
            document.getElementById('dailyLow').innerText = metrics.low.toFixed(2);

            // Źródło Ceny
            document.getElementById('quoteSource').innerText = metrics.quote_source;
        } catch (error) {
            console.error('Błąd w updateMarketMetrics:', error);
        }
    }

    function updateTransactions(data) {
        try {
            var transactions = data.transactions;
            var transactionsContainer = document.getElementById('transactions');
            transactionsContainer.innerHTML = '';

            var largeTransactionThreshold = 1000; // Próg dla dużej transakcji

            transactions.forEach(function(tx) {
                var txRow = document.createElement('div');
                txRow.className = 'transaction-row';
                txRow.innerHTML = `
                    <div class="tx-time">${new Date(tx.timestamp).toLocaleTimeString()}</div>
                    <div class="tx-price">${tx.price.toFixed(2)}</div>
                    <div class="tx-volume">${tx.volume.toFixed(2)}</div>
                `;
                // Kolorowe kodowanie transakcji
                if (tx.type === 'buy') {
                    txRow.style.color = 'green';
                } else {
                    txRow.style.color = 'red';
                }
                // Wyróżnianie dużych transakcji
                if (tx.volume > largeTransactionThreshold) {
                    txRow.style.fontWeight = 'bold';
                    txRow.style.backgroundColor = '#ffeb3b';
                }
                transactionsContainer.appendChild(txRow);
            });

            // Aktualizacja histogramu wolumenu transakcji
            updateTransactionVolumeChart(transactions);
        } catch (error) {
            console.error('Błąd w updateTransactions:', error);
        }
    }

    function updateTransactionVolumeChart(transactions) {
        try {
            var ctx = document.getElementById('transactionVolumeChart').getContext('2d');
            var volumes = transactions.map(tx => tx.volume);
            var times = transactions.map(tx => new Date(tx.timestamp).toLocaleTimeString());

            if (transactionVolumeChart) {
                transactionVolumeChart.data.labels = times;
                transactionVolumeChart.data.datasets[0].data = volumes;
                transactionVolumeChart.update();
            } else {
                transactionVolumeChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: times,
                        datasets: [{
                            label: 'Wolumen Transakcji',
                            data: volumes,
                            backgroundColor: 'rgba(75, 192, 192, 0.6)',
                            borderColor: 'rgba(75, 192, 192, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Czas'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Wolumen'
                                }
                            }
                        }
                    }
                });
            }
        } catch (error) {
            console.error('Błąd w updateTransactionVolumeChart:', error);
        }
    }

    function updateMarketSentiment(data) {
        try {
            var ratio = data.buy_sell_ratio;
            var sentimentElement = document.getElementById('marketSentiment');
            sentimentElement.innerText = (ratio * 100).toFixed(2) + '% kupna';
        } catch (error) {
            console.error('Błąd w updateMarketSentiment:', error);
        }
    }

    function updateDepthChart(data) {
        try {
            var orderBook = data.order_book;
            var levels = Object.values(orderBook);

            var bids = levels.map(level => ({
                price: level.bid,
                volume: level.bidVolume
            })).filter(item => item.volume > 0);

            var asks = levels.map(level => ({
                price: level.ask,
                volume: level.askVolume
            })).filter(item => item.volume > 0);

            // Sortowanie po cenie
            bids.sort((a, b) => b.price - a.price);
            asks.sort((a, b) => a.price - b.price);

            var bidPrices = bids.map(b => b.price);
            var bidVolumes = bids.map((b, i) => bids.slice(0, i + 1).reduce((sum, item) => sum + item.volume, 0));

            var askPrices = asks.map(a => a.price);
            var askVolumes = asks.map((a, i) => asks.slice(0, i + 1).reduce((sum, item) => sum + item.volume, 0));

            var ctx = document.getElementById('depthChart').getContext('2d');

            if (depthChart) {
                depthChart.data.datasets[0].data = bidVolumes;
                depthChart.data.labels = bidPrices.concat(askPrices);
                depthChart.data.datasets[1].data = askVolumes;
                depthChart.update();
            } else {
                depthChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: bidPrices.concat(askPrices),
                        datasets: [
                            {
                                label: 'Bids',
                                data: bidVolumes,
                                backgroundColor: 'rgba(0, 255, 0, 0.2)',
                                borderColor: 'rgba(0, 255, 0, 1)',
                                fill: true,
                                stepped: true
                            },
                            {
                                label: 'Asks',
                                data: askVolumes,
                                backgroundColor: 'rgba(255, 0, 0, 0.2)',
                                borderColor: 'rgba(255, 0, 0, 1)',
                                fill: true,
                                stepped: true
                            }
                        ]
                    },
                    options: {
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Cena'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Skumulowany Wolumen'
                                }
                            }
                        }
                    }
                });
            }

            // Aktualizacja heatmapy
            updateHeatmapChart(levels);
        } catch (error) {
            console.error('Błąd w updateDepthChart:', error);
        }
    }

    function updateHeatmapChart(levels) {
        try {
            var ctx = document.getElementById('heatmapChart').getContext('2d');

            var dataPoints = levels.map(level => ({
                x: level.level,
                y: (level.ask + level.bid) / 2,
                v: (level.askVolume + level.bidVolume) / 2
            }));

            var xLabels = [...new Set(dataPoints.map(dp => dp.x))].sort((a, b) => a - b);
            var yLabels = [...new Set(dataPoints.map(dp => dp.y))].sort((a, b) => a - b);

            var dataMatrix = [];
            xLabels.forEach(function(x, xi) {
                dataMatrix[xi] = [];
                yLabels.forEach(function(y, yi) {
                    var point = dataPoints.find(dp => dp.x === x && dp.y === y);
                    dataMatrix[xi][yi] = point ? point.v : 0;
                });
            });

            var flatData = [];
            for (var i = 0; i < xLabels.length; i++) {
                for (var j = 0; j < yLabels.length; j++) {
                    flatData.push({
                        x: xLabels[i],
                        y: yLabels[j],
                        v: dataMatrix[i][j]
                    });
                }
            }

            if (heatmapChart) {
                heatmapChart.data.datasets[0].data = flatData;
                heatmapChart.update();
            } else {
                heatmapChart = new Chart(ctx, {
                    type: 'matrix',
                    data: {
                        datasets: [{
                            label: 'Heatmap',
                            data: flatData,
                            backgroundColor: function(context) {
                                var value = context.dataset.data[context.dataIndex].v;
                                var alpha = value / Math.max(...context.dataset.data.map(d => d.v));
                                return `rgba(0, 0, 255, ${alpha})`;
                            },
                            width: function(context) {
                                var a = context.chart.chartArea;
                                return (a.right - a.left) / xLabels.length - 1;
                            },
                            height: function(context) {
                                var a = context.chart.chartArea;
                                return (a.bottom - a.top) / yLabels.length - 1;
                            }
                        }]
                    },
                    options: {
                        scales: {
                            x: {
                                type: 'category',
                                labels: xLabels.map(l => 'L' + l),
                                title: {
                                    display: true,
                                    text: 'Poziom'
                                },
                                grid: {
                                    display: false
                                }
                            },
                            y: {
                                type: 'category',
                                labels: yLabels.map(y => y.toFixed(2)),
                                title: {
                                    display: true,
                                    text: 'Cena'
                                },
                                grid: {
                                    display: false
                                }
                            }
                        },
                        plugins: {
                            tooltip: {
                                callbacks: {
                                    title: function() { return ''; },
                                    label: function(context) {
                                        var d = context.dataset.data[context.dataIndex];
                                        return `Poziom: L${d.x}, Cena: ${d.y.toFixed(2)}, Wolumen: ${d.v}`;
                                    }
                                }
                            }
                        }
                    }
                });
            }
        } catch (error) {
            console.error('Błąd w updateHeatmapChart:', error);
        }
    }

    function updateCVDChart(data) {
        try {
            var cvdValue = data.cvd;
            var ctx = document.getElementById('cvdChart').getContext('2d');

            if (cvdChart) {
                cvdChart.data.datasets[0].data.push(cvdValue);
                cvdChart.data.labels.push(new Date().toLocaleTimeString());
                cvdChart.update();
            } else {
                cvdChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: [new Date().toLocaleTimeString()],
                        datasets: [{
                            label: 'Cumulative Volume Delta (CVD)',
                            data: [cvdValue],
                            borderColor: 'rgba(54, 162, 235, 1)',
                            backgroundColor: 'rgba(54, 162, 235, 0.2)',
                            fill: true
                        }]
                    },
                    options: {
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Czas'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'CVD'
                                }
                            }
                        }
                    }
                });
            }
        } catch (error) {
            console.error('Błąd w updateCVDChart:', error);
        }
    }

    function updateRecommendation(data) {
        try {
            var recommendation = data.recommendation;
            document.getElementById('recommendation').innerText = recommendation;
        } catch (error) {
            console.error('Błąd w updateRecommendation:', error);
        }
    }

    function updateFearGreedIndex(data) {
        try {
            var fearGreed = data.fear_greed_index;
            document.getElementById('fearGreedIndex').innerText = fearGreed.toFixed(2);
        } catch (error) {
            console.error('Błąd w updateFearGreedIndex:', error);
        }
    }

    function updateOrderImbalance(data) {
        try {
            var imbalance = data.order_imbalance;
            document.getElementById('orderImbalance').innerText = (imbalance * 100).toFixed(2) + '%';
        } catch (error) {
            console.error('Błąd w updateOrderImbalance:', error);
        }
    }

    function updateMomentum(data) {
        try {
            var momentum = data.momentum;
            var momentumElement = document.getElementById('momentum');
            momentumElement.innerText = momentum.toFixed(2);
            if (momentum > 0) {
                momentumElement.style.color = 'green';
            } else if (momentum < 0) {
                momentumElement.style.color = 'red';
            } else {
                momentumElement.style.color = 'gray';
            }
        } catch (error) {
            console.error('Błąd w updateMomentum:', error);
        }
    }

    function updateTrendDirection(data) {
        try {
            var direction = data.trend_direction;
            var icon = document.getElementById('trendDirectionIcon');
            if (direction === 'up') {
                icon.innerHTML = '↑';
                icon.style.color = 'green';
            } else if (direction === 'down') {
                icon.innerHTML = '↓';
                icon.style.color = 'red';
            } else {
                icon.innerHTML = '→';
                icon.style.color = 'gray';
            }
        } catch (error) {
            console.error('Błąd w updateTrendDirection:', error);
        }
    }

    function updateTrendStrength(data) {
        try {
            var strength = data.trend_strength;
            var strengthElement = document.getElementById('trendStrength');
            strengthElement.innerText = strength.toFixed(2);
            if (strength > 0) {
                strengthElement.style.color = 'green';
            } else if (strength < 0) {
                strengthElement.style.color = 'red';
            } else {
                strengthElement.style.color = 'gray';
            }
        } catch (error) {
            console.error('Błąd w updateTrendStrength:', error);
        }
    }

    function updateSupportResistanceLevels(data) {
        try {
            var supportLevels = data.support_levels;
            var resistanceLevels = data.resistance_levels;
            var levelsContainer = document.getElementById('supportResistanceLevels');
            levelsContainer.innerHTML = `
                <p>Poziomy Wsparcia: ${supportLevels.map(l => l.toFixed(2)).join(', ')}</p>
                <p>Poziomy Oporu: ${resistanceLevels.map(l => l.toFixed(2)).join(', ')}</p>
            `;
        } catch (error) {
            console.error('Błąd w updateSupportResistanceLevels:', error);
        }
    }

    function updateTickChart(data) {
        try {
            var tickData = data.tick_chart;
            var ctx = document.getElementById('tickChart').getContext('2d');

            var prices = tickData.map(t => t.price);
            var times = tickData.map(t => new Date(t.timestamp).toLocaleTimeString());

            if (tickChart) {
                tickChart.data.labels = times;
                tickChart.data.datasets[0].data = prices;
                tickChart.update();
            } else {
                tickChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: times,
                        datasets: [{
                            label: 'Tick Chart',
                            data: prices,
                            borderColor: 'rgba(75, 192, 192, 1)',
                            backgroundColor: 'rgba(75, 192, 192, 0.2)',
                            fill: true
                        }]
                    },
                    options: {
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Czas'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Cena'
                                }
                            }
                        }
                    }
                });
            }
        } catch (error) {
            console.error('Błąd w updateTickChart:', error);
        }
    }

    function updateOrderFlow(data) {
        try {
            var orderFlow = data.order_flow;
            var orderFlowContainer = document.getElementById('orderFlow');
            orderFlowContainer.innerHTML = '';

            var largeTransactionThreshold = 1000; // Próg dla dużej transakcji

            orderFlow.forEach(function(order) {
                var orderRow = document.createElement('div');
                orderRow.className = 'order-row';
                orderRow.innerHTML = `
                    <div class="order-time">${new Date(order.timestamp).toLocaleTimeString()}</div>
                    <div class="order-price">${order.price.toFixed(2)}</div>
                    <div class="order-volume">${order.volume.toFixed(2)}</div>
                    <div class="order-type">${order.type.toUpperCase()}</div>
                `;
                // Kolorowe kodowanie
                if (order.type === 'buy') {
                    orderRow.style.color = 'green';
                } else {
                    orderRow.style.color = 'red';
                }
                // Wyróżnianie dużych transakcji
                if (order.volume > largeTransactionThreshold) {
                    orderRow.style.fontWeight = 'bold';
                    orderRow.style.backgroundColor = '#ffeb3b';
                }
                orderFlowContainer.appendChild(orderRow);
            });
        } catch (error) {
            console.error('Błąd w updateOrderFlow:', error);
        }
    }

    function updateRecentTradeStats(data) {
      
    }
});
