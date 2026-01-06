function ensureMathJax(callback) {
    if (window.mathJaxReady) {
        callback();
    } else {
        const checkInterval = setInterval(() => {
            if (window.mathJaxReady) {
                clearInterval(checkInterval);
                callback();
            }
        }, 100);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Initialize slider value
    const difficultySlider = document.getElementById('difficulty');
    difficultySlider.style.setProperty('--value', difficultySlider.value);

    // Immediately trigger MathJax rendering if content exists
    ensureMathJax(() => {
        const generatedTasks = document.getElementById('generatedTasks');
        const taskSolutions = document.getElementById('taskSolutions');
        if (generatedTasks || taskSolutions) {
            MathJax.typesetPromise([generatedTasks, taskSolutions])
                .catch(err => console.error('Initial MathJax typeset failed:', err));
        }
    });

    // Elements
    const elements = {
        taskTypeSelect: document.getElementById('taskType'),
        examSelectionContainer: document.getElementById('examSelectionContainer'),
        customTopicContainer: document.getElementById('customTopicContainer'),
        fileUploadContainer: document.getElementById('fileUploadContainer'),
        difficultySlider: difficultySlider,
        taskGenerationForm: document.getElementById('taskGenerationForm'),
        taskResults: document.getElementById('taskResults'),
        generatedTasks: document.getElementById('generatedTasks'),
        solutionSection: document.getElementById('solutionSection'),
        taskSolutions: document.getElementById('taskSolutions'),
        showSolutionsBtn: document.getElementById('showSolutionsBtn'),
        exportPdfBtn: document.getElementById('exportPdfBtn'),
        exportSolutionsPdfBtn: document.getElementById('exportSolutionsPdfBtn'),
        saveTasksBtn: document.getElementById('saveTasksBtn'),
        loadingIndicator: document.getElementById('loadingIndicator'),
        generateBtn: document.getElementById('generateBtn'),
        generateText: document.getElementById('generateText'),
        generateSpinner: document.getElementById('generateSpinner'),
        taskCountInput: document.getElementById('taskCount'),
        customTopicInput: document.getElementById('customTopic'),
        examSelectionInput: document.getElementById('examSelection'),
        actionButtons: document.getElementById('actionButtons')
    };

    // Initialize event listeners
    setupEventListeners();

    function updateSliderVisuals(value) {
        elements.difficultySlider.style.setProperty('--value', value);
        document.querySelector('.difficulty-value').textContent = `Stufe: ${value}`;
        
        document.querySelectorAll('.difficulty-labels span').forEach(span => {
            span.classList.toggle('active', parseInt(span.dataset.value) === parseInt(value));
        });
    }

    function setupEventListeners() {
        // Difficulty slider
        elements.difficultySlider.addEventListener('input', function() {
            updateSliderVisuals(this.value);
        });

        // Task type selection
        elements.taskTypeSelect.addEventListener('change', function() {
            const isSpecific = this.value === 'specific';
            const isCustom = this.value === 'custom';
            const isUpload = this.value === 'upload';
            
            elements.examSelectionContainer.style.display = isSpecific ? 'block' : 'none';
            elements.customTopicContainer.style.display = isCustom ? 'block' : 'none';
            elements.fileUploadContainer.style.display = isUpload ? 'block' : 'none';
        });

        // Form submission
        elements.taskGenerationForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            await generateTasks();
        });

        // Show/hide solutions
        elements.showSolutionsBtn.addEventListener('click', function() {
            elements.solutionSection.style.display = 'block';
            this.style.display = 'none';
            elements.exportSolutionsPdfBtn.style.display = 'inline-block';
            if (typeof MathJax !== 'undefined') MathJax.typesetPromise();
        });

        // PDF exports
        elements.exportPdfBtn.addEventListener('click', () => exportToPDF(false));
        elements.exportSolutionsPdfBtn.addEventListener('click', () => exportToPDF(true));
        
        // Save tasks
        elements.saveTasksBtn.addEventListener('click', saveTasksToAccount);
    }

    async function generateTasks() {
        const formData = new FormData();
        formData.append('taskType', elements.taskTypeSelect.value);
        formData.append('difficulty', elements.difficultySlider.value);
        formData.append('taskCount', elements.taskCountInput.value);
        
        if (elements.taskTypeSelect.value === 'specific') {
            formData.append('examSelection', elements.examSelectionInput.value);
        }
        
        if (elements.taskTypeSelect.value === 'custom') {
            formData.append('customTopic', elements.customTopicInput.value.trim());
        }
        
        const fileInput = document.getElementById('fileUpload');
        if (fileInput.files[0]) {
            formData.append('file', fileInput.files[0]);
        }

        // Validate inputs
        if (formData.taskType === 'custom' && !formData.customTopic) {
            alert('Bitte gib ein Thema ein');
            return;
        }

        // Show loading state
        elements.generateBtn.disabled = true;
        elements.generateText.textContent = 'Generierung läuft...';
        elements.generateSpinner.classList.remove('d-none');
        elements.loadingIndicator.style.display = 'block';
        elements.taskResults.style.display = 'block';
        
        // Different message for file uploads
        const loadingMessage = elements.taskTypeSelect.value === 'upload' 
            ? '<div class="alert alert-info"><div class="spinner-border spinner-border-sm me-2"></div>Dokument wird analysiert...</div>'
            : '<div class="alert alert-info"><div class="spinner-border spinner-border-sm me-2"></div>Aufgaben werden generiert...</div>';
        
        elements.generatedTasks.innerHTML = loadingMessage;

        try {
            if (elements.taskTypeSelect.value === 'upload') {
                // Special handling for file uploads - send directly to GPT-4o
                const file = document.getElementById('fileUpload').files[0];
                if (!file) throw new Error('Keine Datei ausgewählt');
                
                const reader = new FileReader();
                reader.onload = async function(e) {
                    try {
                        const base64Content = e.target.result.split(',')[1];
                        const response = await fetch('/process_with_gpt4o', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                filename: file.name,
                                content: base64Content,
                                contentType: file.type
                            })
                        });

                        if (!response.ok) throw new Error(await response.text());
                        const result = await response.json();
                        
                        if (!result.content) throw new Error('Keine Antwort von KI erhalten');
                        displayTasks(result.content, '');
                    } catch (error) {
                        console.error('Error processing with GPT-4o:', error);
                        elements.generatedTasks.innerHTML = `<div class="alert alert-danger">Fehler: ${error.message}</div>`;
                    } finally {
                        elements.generateBtn.disabled = false;
                        elements.generateText.textContent = 'Aufgaben generieren';
                        elements.generateSpinner.classList.add('d-none');
                        elements.loadingIndicator.style.display = 'none';
                    }
                };
                reader.readAsDataURL(file);
                return; // Exit early since we're handling the async operation via FileReader
            } else {
                // Normal task generation flow
                const response = await fetch('/generate_tasks', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                
                if (!response.ok || data.error) {
                    const errorMsg = data.error || await response.text() || 'Server error';
                    if (data.tasksheet) {
                        // Partial success - show tasks with warning
                        displayTasks(data.tasksheet, data.solutionsheet || '');
                        elements.generatedTasks.insertAdjacentHTML('afterbegin', 
                            `<div class="alert alert-warning">${errorMsg}</div>`);
                    } else {
                        throw new Error(errorMsg);
                    }
                } else {
                    if (!data.tasksheet) {
                        throw new Error('Keine Aufgaben erhalten');
                    }
                    displayTasks(data.tasksheet, data.solutionsheet || '');
                }
            }
        } catch (error) {
            console.error('Error generating tasks:', error);
            elements.generatedTasks.innerHTML = `<div class="alert alert-danger">Fehler: ${error.message}</div>`;
        } finally {
            elements.generateBtn.disabled = false;
            elements.generateText.textContent = 'Aufgaben generieren';
            elements.generateSpinner.classList.add('d-none');
            elements.loadingIndicator.style.display = 'none';
        }
    }

    function renderMarkdownWithMath(content) {
        try {
            if (!content) return '<div class="markdown-content">Kein Inhalt verfügbar</div>';
            
            // First protect LaTeX blocks from Markdown processing
            const protected = content.replace(/(\\\(.*?\\\)|\\\[.*?\\\])/gs, 
                match => `%%MATHJAX:${btoa(match)}%%`);
            
            // Process Markdown
            const dirty = marked.parse(protected);
            const clean = DOMPurify.sanitize(dirty, {
                ADD_TAGS: ['iframe', 'mjx-container'],
                ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'jax', 'display']
            });
            
            // Restore LaTeX blocks
            const withMath = clean.replace(/%%MATHJAX:(.*?)%%/gs, 
                (_, encoded) => atob(encoded));
            
            return `<div class="markdown-content math-container">${withMath}</div>`;
        } catch (error) {
            console.error('Markdown rendering error:', error);
            return `<div class="markdown-content">${content}</div>`;
        }
    }

    function displayTasks(tasksheet, solutionsheet) {
        try {
            if (!tasksheet) {
                throw new Error('No tasks content received');
            }

            elements.generatedTasks.innerHTML = renderMarkdownWithMath(tasksheet);
            elements.taskSolutions.innerHTML = solutionsheet ? renderMarkdownWithMath(solutionsheet) : '';
            
            elements.showSolutionsBtn.style.display = solutionsheet ? 'block' : 'none';
            elements.exportSolutionsPdfBtn.style.display = 'none';
            elements.taskResults.style.display = 'block';
            elements.actionButtons.style.display = 'flex';

            // Immediately render math after tasks are displayed
            if (typeof MathJax !== 'undefined') {
                MathJax.typesetPromise([elements.generatedTasks])
                    .catch(err => console.error('MathJax initial render failed:', err));
            }

            // EXACT solution button behavior replicated immediately
            ensureMathJax(() => {
                MathJax.typesetPromise([elements.generatedTasks, elements.taskSolutions])
                    .then(() => {
                        console.log('Initial math rendering complete');
                        // Also set up the solution button for later
                        elements.showSolutionsBtn.addEventListener('click', function() {
                            elements.solutionSection.style.display = 'block';
                            this.style.display = 'none';
                        }, {once: true});
                    })
                    .catch(err => {
                        console.error('Initial MathJax typeset failed:', err);
                        setTimeout(() => {
                            MathJax.typesetPromise([elements.generatedTasks, elements.taskSolutions])
                                .catch(e => console.error('Final MathJax retry failed:', e));
                        }, 500);
                    });
            });
        } catch (error) {
            console.error('Error displaying tasks:', error);
            elements.generatedTasks.innerHTML = `<div class="alert alert-danger">Error displaying tasks: ${error.message}</div>`;
        }
    }

    async function exportToPDF(exportSolutions = false) {
        try {
            const button = exportSolutions ? elements.exportSolutionsPdfBtn : elements.exportPdfBtn;
            button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> PDF wird erstellt...';

            const contentElement = exportSolutions ? elements.taskSolutions : elements.generatedTasks;
            if (!contentElement || !contentElement.textContent.trim()) {
                throw new Error(exportSolutions ? 'Lösungen müssen zuerst angezeigt werden' : 'Keine Aufgaben vorhanden');
            }

            // Get clean HTML content with proper math rendering
            const content = contentElement.innerHTML;
            const title = `Gymiboost ${exportSolutions ? 'Lösungen' : 'Aufgaben'}`;
            const date = new Date().toLocaleDateString('de-CH');

            // Send to server for PDF generation
            const response = await fetch('/generate_pdf', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title: title,
                    date: date,
                    content: content,
                    type: exportSolutions ? 'solutions' : 'tasks'
                })
            });

            if (!response.ok) {
                throw new Error(await response.text());
            }

            // Download the PDF
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `gymiboost-${exportSolutions ? 'loesungen' : 'aufgaben'}-${new Date().toISOString().slice(0,10)}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error('PDF Export Error:', error);
            alert('Fehler beim PDF-Export: ' + error.message);
        } finally {
            const button = exportSolutions ? elements.exportSolutionsPdfBtn : elements.exportPdfBtn;
            button.disabled = false;
            button.innerHTML = `<i class="bi bi-file-earmark-pdf"></i> ${exportSolutions ? 'Lösungen' : 'Aufgaben'} als PDF`;
        }
    }

    async function saveTasksToAccount() {
        const saveBtn = elements.saveTasksBtn;
        try {
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Speichern...';

            const title = prompt('Gib einen Namen für diese Aufgaben ein:', `Aufgaben vom ${new Date().toLocaleDateString('de-CH')}`);
            if (!title) return;
            
            const topic = prompt('Optional: Gib ein Thema für diese Aufgaben ein (z.B. Bruchrechnen, Satzglieder):', '');
            
            const saveRequest = await fetch('/save_tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    title: title,
                    topic: topic || '',
                    tasksheet: elements.generatedTasks.textContent || elements.generatedTasks.innerText,
                    solutionsheet: elements.taskSolutions.textContent || elements.taskSolutions.innerText
                })
            });

            if (!saveRequest.ok) throw new Error(await saveRequest.text());
            const resultData = await saveRequest.json();
            if (!resultData?.success) throw new Error(resultData?.message || 'Fehler beim Speichern');

            alert('Aufgaben erfolgreich gespeichert');
            
            if (confirm('Möchtest du zu deinen gespeicherten Aufgaben wechseln?')) {
                window.location.href = '/saved_tasks';
            }
        } catch (error) {
            alert('Fehler beim Speichern: ' + error.message);
        } finally {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="bi bi-save"></i> Aufgaben speichern';
        }
    }
});