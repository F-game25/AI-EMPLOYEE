import express from 'express';
import cors from 'cors';
import { brainRouter } from './api/brain.routes';

const app = express();
const port = Number(process.env.PORT || 8899);

app.use(cors());
app.use(express.json({ limit: '2mb' }));

app.get('/health', (_req, res) => {
  res.json({ ok: true, service: 'ai-brain-system', timestamp: Date.now() });
});

app.use('/api/brain', brainRouter);

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`[ai-brain-system] server listening on :${port}`);
});
