const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

// 配置
const PORT = process.env.PORT || 8899;
const AUTO_SAVE_INTERVAL = 30000; // 30秒自动保存

// MIME类型
const MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.mp4': 'video/mp4',
    '.wav': 'audio/wav',
    '.png': 'image/png',
    '.jpg': 'image/jpeg'
};

class ReviewServer {
    constructor(port) {
        this.port = port;
        this.dataDir = '';
        this.autoSaveTimer = null;
    }

    start(dataDir, videoFile) {
        this.dataDir = dataDir;
        this.videoFile = videoFile;

        const self = this;
        const server = http.createServer(function(req, res) {
            self.handleRequest(req, res);
        });

        server.listen(this.port, () => {
            console.log('审核服务器已启动: http://localhost:' + this.port);
            console.log('视频文件: ' + videoFile);
            console.log('数据目录: ' + dataDir);
        });

        // 启动自动保存定时器
        this.startAutoSave();
    }

    startAutoSave() {
        this.autoSaveTimer = setInterval(() => {
            this.autoSave();
        }, AUTO_SAVE_INTERVAL);
    }

    autoSave() {
        // 这个会在有变更时自动保存
    }

    sendJSON(res, data) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(data));
    }

    handleRequest(req, res) {
        const parsedUrl = url.parse(req.url, true);
        const pathname = parsedUrl.pathname;

        // CORS
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

        if (req.method === 'OPTIONS') {
            res.writeHead(200);
            res.end();
            return;
        }

        // API 路由
        if (pathname === '/api/data' && req.method === 'GET') {
            this.sendJSON(res, this.loadData());
            return;
        }

        if (pathname === '/api/data' && req.method === 'POST') {
            let body = '';
            req.on('data', chunk => body += chunk);
            req.on('end', () => {
                const data = JSON.parse(body);
                this.saveData(data);
                this.sendJSON(res, { success: true });
            });
            return;
        }

        if (pathname === '/api/video') {
            this.serveVideo(res);
            return;
        }

        if (pathname === '/api/execute-cut') {
            this.executeCut(res);
            return;
        }

        // 静态文件
        let filePath = pathname === '/' ? '/index.html' : pathname;
        filePath = path.join(__dirname, 'public', filePath);

        this.serveStaticFile(res, filePath);
    }

    loadData() {
        const dataFile = path.join(this.dataDir, 'auto_selected.json');
        if (fs.existsSync(dataFile)) {
            return JSON.parse(fs.readFileSync(dataFile, 'utf-8'));
        }
        return { segments: [], auto_selected: [], silences: [] };
    }

    saveData(data) {
        const dataFile = path.join(this.dataDir, 'user_confirmed.json');
        fs.writeFileSync(dataFile, JSON.stringify(data, null, 2));
    }

    serveVideo(res) {
        if (this.videoFile && fs.existsSync(this.videoFile)) {
            const stat = fs.statSync(this.videoFile);
            const fileSize = stat.size;

            res.writeHead(200, {
                'Content-Type': 'video/mp4',
                'Content-Length': fileSize,
                'Accept-Ranges': 'bytes'
            });

            const readStream = fs.createReadStream(this.videoFile);
            readStream.pipe(res);
        } else {
            res.writeHead(404);
            res.end('Video not found');
        }
    }

    executeCut(res) {
        // 读取用户确认的删除列表
        const confirmedFile = path.join(this.dataDir, 'user_confirmed.json');
        if (!fs.existsSync(confirmedFile)) {
            res.writeHead(400, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: '未找到用户确认数据' }));
            return;
        }

        const confirmed = JSON.parse(fs.readFileSync(confirmedFile, 'utf-8'));
        const toDelete = confirmed.to_delete || [];

        if (toDelete.length === 0) {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ message: '没有需要删除的片段' }));
            return;
        }

        // 生成FFmpeg命令
        const outputFile = path.join(this.dataDir, '..', '..', 'output.mp4');
        const segments = toDelete.map(t => ({ start: t.start, end: t.end }));

        // 这里会调用实际的cut脚本
        const exec = require('child_process').exec;
        const cutScript = path.join(__dirname, 'cut_video.sh');
        const cmd = 'bash "' + cutScript + '" "' + this.videoFile + '" "' + outputFile + '" "' + JSON.stringify(segments) + '"';

        exec(cmd, (error, stdout, stderr) => {
            if (error) {
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: error.message }));
                return;
            }
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ success: true, output: outputFile }));
        });
    }

    serveStaticFile(res, filePath) {
        const ext = path.extname(filePath);
        const contentType = MIME_TYPES[ext] || 'text/plain';

        if (fs.existsSync(filePath)) {
            res.writeHead(200, { 'Content-Type': contentType });
            res.end(fs.readFileSync(filePath));
        } else {
            res.writeHead(404);
            res.end('Not found');
        }
    }
}

// 主程序
if (require.main === module) {
    const dataDir = process.argv[2] || './output';
    const videoFile = process.argv[3] || './video.mp4';

    const server = new ReviewServer(PORT);
    server.start(dataDir, videoFile);
}

module.exports = ReviewServer;