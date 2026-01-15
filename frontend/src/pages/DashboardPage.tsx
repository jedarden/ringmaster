import { useCards } from '../hooks/useCards';
import { useAllLoops } from '../hooks/useLoops';
import { useCardStore } from '../store/cardStore';
import { useLoopStore } from '../store/loopStore';
import { BarChart3, Activity, DollarSign, CheckCircle, TrendingUp, AlertTriangle } from 'lucide-react';
import { Spinner } from '../components/ui/Spinner';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: string;
  trendUp?: boolean;
  color: 'blue' | 'green' | 'yellow' | 'red' | 'purple';
}

function StatCard({ title, value, icon, trend, trendUp, color }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-900/50 border-blue-700 text-blue-400',
    green: 'bg-green-900/50 border-green-700 text-green-400',
    yellow: 'bg-yellow-900/50 border-yellow-700 text-yellow-400',
    red: 'bg-red-900/50 border-red-700 text-red-400',
    purple: 'bg-purple-900/50 border-purple-700 text-purple-400',
  };

  return (
    <div className={`rounded-lg border p-6 ${colorClasses[color]}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-400">{title}</p>
          <p className="text-3xl font-bold mt-1">{value}</p>
          {trend && (
            <p className={`text-sm mt-2 flex items-center gap-1 ${trendUp ? 'text-green-400' : 'text-red-400'}`}>
              <TrendingUp className={`w-4 h-4 ${!trendUp && 'rotate-180'}`} />
              {trend}
            </p>
          )}
        </div>
        <div className="text-4xl opacity-50">{icon}</div>
      </div>
    </div>
  );
}

interface StateDistributionProps {
  distribution: Record<string, number>;
}

function StateDistribution({ distribution }: StateDistributionProps) {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0);

  const stateColors: Record<string, string> = {
    DRAFT: 'bg-gray-500',
    PLANNING: 'bg-blue-500',
    CODING: 'bg-purple-500',
    CODE_REVIEW: 'bg-indigo-500',
    TESTING: 'bg-cyan-500',
    BUILD_QUEUE: 'bg-yellow-500',
    BUILDING: 'bg-orange-500',
    BUILD_SUCCESS: 'bg-lime-500',
    BUILD_FAILED: 'bg-red-500',
    DEPLOY_QUEUE: 'bg-teal-500',
    DEPLOYING: 'bg-emerald-500',
    VERIFYING: 'bg-sky-500',
    COMPLETED: 'bg-green-500',
    ERROR_FIXING: 'bg-rose-500',
    ARCHIVED: 'bg-stone-500',
    FAILED: 'bg-red-600',
  };

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
      <h3 className="text-lg font-semibold mb-4">Card Distribution by State</h3>
      <div className="space-y-3">
        {Object.entries(distribution)
          .filter(([_, count]) => count > 0)
          .sort(([, a], [, b]) => b - a)
          .map(([state, count]) => (
            <div key={state} className="flex items-center gap-3">
              <div className="w-24 text-sm text-gray-400 truncate">{state}</div>
              <div className="flex-1 h-6 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full ${stateColors[state] || 'bg-gray-500'} transition-all duration-500`}
                  style={{ width: `${(count / total) * 100}%` }}
                />
              </div>
              <div className="w-12 text-right text-sm font-medium">{count}</div>
            </div>
          ))}
      </div>
      {total === 0 && (
        <p className="text-gray-500 text-center py-8">No cards yet</p>
      )}
    </div>
  );
}

function RecentActivity() {
  const cards = useCardStore((s) => Array.from(s.cards.values()));
  const recentCards = cards
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
    .slice(0, 5);

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
      <h3 className="text-lg font-semibold mb-4">Recent Activity</h3>
      <div className="space-y-4">
        {recentCards.map((card) => (
          <div key={card.id} className="flex items-start gap-3 pb-4 border-b border-gray-700 last:border-0 last:pb-0">
            <div className="w-2 h-2 mt-2 rounded-full bg-blue-500" />
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{card.title}</p>
              <p className="text-sm text-gray-400">
                {card.state} - Updated {new Date(card.updatedAt).toLocaleDateString()}
              </p>
            </div>
          </div>
        ))}
        {recentCards.length === 0 && (
          <p className="text-gray-500 text-center py-4">No recent activity</p>
        )}
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { isLoading: cardsLoading } = useCards(null);
  const { isLoading: loopsLoading } = useAllLoops();
  const cards = useCardStore((s) => Array.from(s.cards.values()));
  const loops = useLoopStore((s) => s.activeLoops);

  if (cardsLoading || loopsLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner size="lg" />
      </div>
    );
  }

  // Calculate stats
  const totalCards = cards.length;
  const activeLoops = Array.from(loops.values()).filter(l => l.status === 'running').length;
  const pausedLoops = Array.from(loops.values()).filter(l => l.status === 'paused').length;
  const completedCards = cards.filter(c => c.state === 'completed').length;
  const errorCards = cards.filter(c => c.state === 'error_fixing' || c.state === 'failed').length;

  // Calculate cost (from loops)
  const totalCost = Array.from(loops.values()).reduce((sum, loop) => sum + (loop.totalCostUsd || 0), 0);

  // Success rate
  const successRate = totalCards > 0 ? Math.round((completedCards / totalCards) * 100) : 0;

  // State distribution
  const stateDistribution: Record<string, number> = {};
  cards.forEach(card => {
    stateDistribution[card.state] = (stateDistribution[card.state] || 0) + 1;
  });

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Cards"
          value={totalCards}
          icon={<BarChart3 className="w-10 h-10" />}
          color="blue"
        />
        <StatCard
          title="Active Loops"
          value={`${activeLoops} running, ${pausedLoops} paused`}
          icon={<Activity className="w-10 h-10" />}
          color="green"
        />
        <StatCard
          title="Today's Cost"
          value={`$${totalCost.toFixed(2)}`}
          icon={<DollarSign className="w-10 h-10" />}
          color="yellow"
        />
        <StatCard
          title="Success Rate"
          value={`${successRate}%`}
          icon={<CheckCircle className="w-10 h-10" />}
          trend={errorCards > 0 ? `${errorCards} errors` : undefined}
          trendUp={false}
          color={successRate >= 75 ? 'green' : successRate >= 50 ? 'yellow' : 'red'}
        />
      </div>

      {/* Charts and Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <StateDistribution distribution={stateDistribution} />
        <RecentActivity />
      </div>

      {/* Error Cards Alert */}
      {errorCards > 0 && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 flex items-center gap-4">
          <AlertTriangle className="w-8 h-8 text-red-400" />
          <div>
            <h4 className="font-semibold text-red-300">Cards Need Attention</h4>
            <p className="text-sm text-red-400">
              {errorCards} card{errorCards > 1 ? 's' : ''} in error state require manual intervention.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
