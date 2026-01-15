import { useState } from 'react';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Github, Cloud, Cpu, Key, Save, RefreshCw, CheckCircle, XCircle } from 'lucide-react';

interface IntegrationConfig {
  enabled: boolean;
  endpoint?: string;
  token?: string;
}

interface LoopDefaults {
  maxIterations: number;
  maxRuntimeSeconds: number;
  maxCostUsd: number;
  checkpointInterval: number;
  cooldownSeconds: number;
  completionSignal: string;
}

function SettingSection({ title, icon, children }: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
      <div className="flex items-center gap-3 mb-4">
        {icon}
        <h2 className="text-lg font-semibold">{title}</h2>
      </div>
      {children}
    </div>
  );
}

function IntegrationStatus({ connected }: { connected: boolean }) {
  return connected ? (
    <span className="flex items-center gap-1 text-sm text-green-400">
      <CheckCircle className="w-4 h-4" /> Connected
    </span>
  ) : (
    <span className="flex items-center gap-1 text-sm text-gray-400">
      <XCircle className="w-4 h-4" /> Not configured
    </span>
  );
}

export function SettingsPage() {
  const [github, setGithub] = useState<IntegrationConfig>({
    enabled: false,
    token: '',
  });

  const [argocd, setArgocd] = useState<IntegrationConfig>({
    enabled: false,
    endpoint: '',
    token: '',
  });

  const [claude, setClaude] = useState<IntegrationConfig>({
    enabled: true,
    token: '',
  });

  const [loopDefaults, setLoopDefaults] = useState<LoopDefaults>({
    maxIterations: 50,
    maxRuntimeSeconds: 3600,
    maxCostUsd: 5.0,
    checkpointInterval: 5,
    cooldownSeconds: 3,
    completionSignal: 'TASK_COMPLETE',
  });

  const handleSaveGithub = () => {
    // Save to localStorage for now
    localStorage.setItem('ringmaster_github', JSON.stringify(github));
    alert('GitHub settings saved');
  };

  const handleSaveArgocd = () => {
    localStorage.setItem('ringmaster_argocd', JSON.stringify(argocd));
    alert('ArgoCD settings saved');
  };

  const handleSaveClaude = () => {
    localStorage.setItem('ringmaster_claude', JSON.stringify(claude));
    alert('Claude API settings saved');
  };

  const handleSaveLoopDefaults = () => {
    localStorage.setItem('ringmaster_loop_defaults', JSON.stringify(loopDefaults));
    alert('Loop defaults saved');
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Settings</h1>
      </div>

      {/* Claude API Settings */}
      <SettingSection title="Claude API" icon={<Cpu className="w-5 h-5 text-purple-400" />}>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">Status</span>
            <IntegrationStatus connected={!!claude.token} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">API Key</label>
            <Input
              type="password"
              value={claude.token}
              onChange={(e) => setClaude({ ...claude, token: e.target.value })}
              placeholder="sk-ant-api..."
            />
            <p className="text-xs text-gray-500 mt-1">
              Your Anthropic API key. Get one at console.anthropic.com
            </p>
          </div>
          <Button onClick={handleSaveClaude} size="sm">
            <Save className="w-4 h-4 mr-2" />
            Save Claude Settings
          </Button>
        </div>
      </SettingSection>

      {/* GitHub Settings */}
      <SettingSection title="GitHub Actions" icon={<Github className="w-5 h-5 text-white" />}>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">Status</span>
            <IntegrationStatus connected={!!github.token} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Personal Access Token</label>
            <Input
              type="password"
              value={github.token}
              onChange={(e) => setGithub({ ...github, token: e.target.value })}
              placeholder="ghp_..."
            />
            <p className="text-xs text-gray-500 mt-1">
              Token needs repo and workflow permissions
            </p>
          </div>
          <Button onClick={handleSaveGithub} size="sm">
            <Save className="w-4 h-4 mr-2" />
            Save GitHub Settings
          </Button>
        </div>
      </SettingSection>

      {/* ArgoCD Settings */}
      <SettingSection title="ArgoCD" icon={<Cloud className="w-5 h-5 text-orange-400" />}>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">Status</span>
            <IntegrationStatus connected={!!argocd.endpoint && !!argocd.token} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Server URL</label>
            <Input
              value={argocd.endpoint}
              onChange={(e) => setArgocd({ ...argocd, endpoint: e.target.value })}
              placeholder="https://argocd.example.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Auth Token</label>
            <Input
              type="password"
              value={argocd.token}
              onChange={(e) => setArgocd({ ...argocd, token: e.target.value })}
              placeholder="argocd-token..."
            />
          </div>
          <Button onClick={handleSaveArgocd} size="sm">
            <Save className="w-4 h-4 mr-2" />
            Save ArgoCD Settings
          </Button>
        </div>
      </SettingSection>

      {/* Loop Defaults */}
      <SettingSection title="Loop Defaults" icon={<RefreshCw className="w-5 h-5 text-blue-400" />}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">Max Iterations</label>
            <Input
              type="number"
              value={loopDefaults.maxIterations}
              onChange={(e) => setLoopDefaults({ ...loopDefaults, maxIterations: parseInt(e.target.value) || 50 })}
              min={1}
              max={1000}
            />
            <p className="text-xs text-gray-500 mt-1">Maximum LLM calls per loop</p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Max Runtime (seconds)</label>
            <Input
              type="number"
              value={loopDefaults.maxRuntimeSeconds}
              onChange={(e) => setLoopDefaults({ ...loopDefaults, maxRuntimeSeconds: parseInt(e.target.value) || 3600 })}
              min={60}
              max={86400}
            />
            <p className="text-xs text-gray-500 mt-1">Maximum loop duration</p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Max Cost (USD)</label>
            <Input
              type="number"
              value={loopDefaults.maxCostUsd}
              onChange={(e) => setLoopDefaults({ ...loopDefaults, maxCostUsd: parseFloat(e.target.value) || 5.0 })}
              min={0.1}
              max={100}
              step={0.1}
            />
            <p className="text-xs text-gray-500 mt-1">Budget limit per loop</p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Checkpoint Interval</label>
            <Input
              type="number"
              value={loopDefaults.checkpointInterval}
              onChange={(e) => setLoopDefaults({ ...loopDefaults, checkpointInterval: parseInt(e.target.value) || 5 })}
              min={1}
              max={50}
            />
            <p className="text-xs text-gray-500 mt-1">Save state every N iterations</p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Cooldown (seconds)</label>
            <Input
              type="number"
              value={loopDefaults.cooldownSeconds}
              onChange={(e) => setLoopDefaults({ ...loopDefaults, cooldownSeconds: parseInt(e.target.value) || 3 })}
              min={0}
              max={60}
            />
            <p className="text-xs text-gray-500 mt-1">Delay between iterations</p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Completion Signal</label>
            <Input
              value={loopDefaults.completionSignal}
              onChange={(e) => setLoopDefaults({ ...loopDefaults, completionSignal: e.target.value })}
              placeholder="TASK_COMPLETE"
            />
            <p className="text-xs text-gray-500 mt-1">Text to detect task completion</p>
          </div>
        </div>
        <div className="mt-4">
          <Button onClick={handleSaveLoopDefaults} size="sm">
            <Save className="w-4 h-4 mr-2" />
            Save Loop Defaults
          </Button>
        </div>
      </SettingSection>

      {/* Environment Info */}
      <SettingSection title="Environment" icon={<Key className="w-5 h-5 text-gray-400" />}>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-400">API Endpoint</span>
            <span className="font-mono">{window.location.origin}/api</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">WebSocket</span>
            <span className="font-mono">ws://{window.location.host}/api/ws</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Version</span>
            <span className="font-mono">0.1.0</span>
          </div>
        </div>
      </SettingSection>
    </div>
  );
}
