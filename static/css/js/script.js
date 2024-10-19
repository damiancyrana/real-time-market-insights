document.addEventListener("DOMContentLoaded", function() {
    var ws = new WebSocket("ws://" + window.location.host + "/ws");
    ws.onmessage = function(event) {
        var data = JSON.parse(event.data);
        processData(data);
    };
    ws.onerror = function(event) {
        console.error("WebSocket error observed:", event);
    };

    var canvas = document.getElementById('weavingCanvas');
    var ctx = canvas.getContext('2d');

    var threads = [];

    function processData(data) {
        var symbol = data.symbol;
        var orderBook = data.order_book;

        for (var level in orderBook) {
            var levelData = orderBook[level];
            var bidThread = createThread(levelData, 'right');
            var askThread = createThread(levelData, 'left');
            threads.push(bidThread);
            threads.push(askThread);
        }
    }

    function createThread(levelData, direction) {
        var volume = direction === 'right' ? levelData.bidVolume : levelData.askVolume;

        var thread = {
            x: direction === 'right' ? 0 : canvas.width,
            y: canvas.height / 2,
            color: getColorBasedOnVolume(volume),
            speed: 2 + Math.random() * 3,
            direction: direction,
            amplitude: 50 + Math.random() * 50,
            frequency: 0.01 + Math.random() * 0.02,
            phase: 0,
            volume: volume,
        };
        return thread;
    }

    function getColorBasedOnVolume(volume) {
        var maxVolume = 1000; // Dostosuj według potrzeb
        var ratio = Math.min(volume / maxVolume, 1);
        var red = Math.floor(255 * ratio);
        var green = Math.floor(255 * (1 - ratio));
        return 'rgb(' + red + ',' + green + ',0)';
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        for (var i = 0; i < threads.length; i++) {
            var thread = threads[i];

            if (thread.direction === 'right') {
                thread.x += thread.speed;
                if (thread.x > canvas.width) {
                    threads.splice(i, 1);
                    i--;
                    continue;
                }
            } else {
                thread.x -= thread.speed;
                if (thread.x < 0) {
                    threads.splice(i, 1);
                    i--;
                    continue;
                }
            }

            thread.phase += thread.frequency;
            thread.y = canvas.height / 2 + thread.amplitude * Math.sin(thread.phase);

            drawThread(thread);
        }

        requestAnimationFrame(animate);
    }

    function drawThread(thread) {
        ctx.beginPath();
        ctx.moveTo(thread.x - (thread.direction === 'right' ? thread.speed : -thread.speed), thread.prevY || thread.y);
        ctx.lineTo(thread.x, thread.y);
        ctx.strokeStyle = thread.color;
        ctx.lineWidth = 1 + (thread.volume / 100); // Dostosuj dzielnik według potrzeb
        ctx.stroke();
        thread.prevY = thread.y;
    }

    animate();
});
