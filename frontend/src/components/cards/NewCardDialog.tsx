import { useState } from 'react';
import { Dialog, DialogHeader, DialogContent, DialogFooter } from '../ui/Dialog';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Textarea } from '../ui/Textarea';
import { Select } from '../ui/Select';
import { useUIStore } from '../../store/uiStore';
import { useProjects } from '../../hooks/useProjects';
import { useCreateCard } from '../../hooks/useCards';

export function NewCardDialog() {
  const { showNewCardDialog, setShowNewCardDialog, selectedProjectId } = useUIStore();
  const { projects } = useProjects();
  const createCard = useCreateCard();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [taskPrompt, setTaskPrompt] = useState('');
  const [projectId, setProjectId] = useState(selectedProjectId || '');
  const [priority, setPriority] = useState(0);

  const handleClose = () => {
    setShowNewCardDialog(false);
    // Reset form
    setTitle('');
    setDescription('');
    setTaskPrompt('');
    setProjectId(selectedProjectId || '');
    setPriority(0);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!title || !projectId || !taskPrompt) return;

    try {
      await createCard.mutateAsync({
        projectId,
        title,
        description: description || undefined,
        taskPrompt,
        priority,
      });
      handleClose();
    } catch (err) {
      console.error('Failed to create card:', err);
    }
  };

  return (
    <Dialog open={showNewCardDialog} onClose={handleClose}>
      <form onSubmit={handleSubmit}>
        <DialogHeader onClose={handleClose}>Create New Card</DialogHeader>

        <DialogContent className="space-y-4">
          {/* Project */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Project *
            </label>
            <Select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              required
            >
              <option value="">Select a project</option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>

          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Title *
            </label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Card title"
              required
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Description
            </label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description"
            />
          </div>

          {/* Task Prompt */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Task Prompt *
            </label>
            <Textarea
              value={taskPrompt}
              onChange={(e) => setTaskPrompt(e.target.value)}
              placeholder="Describe what you want the AI to accomplish..."
              rows={4}
              required
            />
          </div>

          {/* Priority */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Priority
            </label>
            <Select
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
            >
              <option value={0}>None</option>
              <option value={1}>P1 - Critical</option>
              <option value={2}>P2 - High</option>
              <option value={3}>P3 - Medium</option>
              <option value={4}>P4 - Low</option>
            </Select>
          </div>
        </DialogContent>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={createCard.isPending || !title || !projectId || !taskPrompt}
          >
            {createCard.isPending ? 'Creating...' : 'Create Card'}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
