document.addEventListener('DOMContentLoaded', () => {
            const userInput = document.getElementById('user-input');
            const sendButton = document.getElementById('send-button');
            const chatBox = document.getElementById('chat-box');
            const headingLink = document.querySelector('h1 a');
            const navButtons = document.querySelectorAll('.nav-button');
            const eventLog = document.getElementById('eventLog');
            const eventLogContent = document.getElementById('event-log-content');
            const chatContainer = document.getElementById('chatBox');
            const chatHeader = document.getElementById('chatHeader');


            function addMessage(content, sender, isHtml = false) {
                const messageDiv = document.createElement('div');
                messageDiv.classList.add('message', sender);
                messageDiv.innerHTML = `${sender === 'user' ? '👤' : '🤖'} ${isHtml ? content : content.replace(/</g, "&lt;").replace(/>/g, "&gt;")}`;
                chatBox.appendChild(messageDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function addEventLogItem(eventType, author, message) {
                const eventItem = document.createElement('div');
                eventItem.classList.add('event-item');
                if (eventType === 'user') {
                    eventItem.classList.add('user-event');
                } else if (eventType === 'agent') {
                    eventItem.classList.add('agent-event');
                } else {
                    eventItem.classList.add('system-event');
                }

                const title = document.createElement('div');
                title.classList.add('event-title');
                title.textContent = `${author} - ${eventType.charAt(0).toUpperCase() + eventType.slice(1)}`;

                const messageText = document.createElement('p');
                messageText.classList.add('event-message');
                messageText.textContent = message;
                

                eventItem.appendChild(title);
                eventItem.appendChild(messageText);
                eventLogContent.appendChild(eventItem);
                eventLogContent.scrollTop = eventLogContent.scrollHeight;
            }

            async function sendMessage() {
            const message = userInput.value.trim();
            if (!message) return;

            addMessage(message, 'user');
            addEventLogItem('user', 'Aryan', `--- Received message: ${message} ---`);
            userInput.value = '';
            sendButton.disabled = true;

    const typingDiv = document.createElement('div');
    typingDiv.classList.add('message', 'agent');
    typingDiv.id = 'typing-indicator';
    typingDiv.textContent = '🤖 typing...';
    chatBox.appendChild(typingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message })
        });

        const currentTypingIndicator = document.getElementById('typing-indicator');
        if (currentTypingIndicator) {
            currentTypingIndicator.remove();
        }

        if (!response.ok) {
            let errorDetail = `HTTP error! status: ${response.status}`;
            try {
                const errorBody = await response.json();
                if (errorBody && errorBody.response) {
                    errorDetail = `Error from server: ${errorBody.response}`;
                } else if (errorBody && errorBody.detail) {
                    errorDetail = `Server validation error: ${errorBody.detail}`;
                } else {
                    errorDetail = `HTTP error! status: ${response.status} - ${response.statusText}`;
                }
            } catch (jsonError) {
                errorDetail = `HTTP error! status: ${response.status} - ${response.statusText}`;
            }
            addMessage(`Error processing your request: ${errorDetail}`, 'agent');
            addEventLogItem('agent', 'Shopping Assistant', `---> Captured final response text event from  Shopping Assistant: Error processing your request: ${errorDetail}`);

        } else {
            const data = await response.json();
            const events = data.events || [];

            events.forEach(event => {
                if (event.type === 'final_response') {
                    addMessage(event.text, 'agent');
                    addEventLogItem('agent', event.agent_name || 'Shopping Assistant', `---> Captured final response text event from ${event.agent_name || 'Shopping Assistant'}: ${event.text} ---`);
                } else if (event.type === 'agent_transfer') {
                    addEventLogItem('system', 'System', `Transferring from ${event.from} to ${event.to}`);
                } else if (event.type === 'error') {
                    addMessage(`Error: ${event.message}`, 'agent');
                    addEventLogItem('system', 'Error', event.message);
                } else if (event.type === 'intermediate_message') {
                    // You can choose to log these or display them in the chat as well
                    console.log(`Intermediate message from ${event.author}: ${event.text}`);
                    addEventLogItem('agent', event.author, event.text); // Log intermediate messages
                }
            });
        }

    } catch (error) {
        console.error('Fetch or unexpected error:', error);
        const currentTypingIndicator = document.getElementById('typing-indicator');
        if (currentTypingIndicator) {
            currentTypingIndicator.remove();
        }
        addMessage(`An unexpected error occurred: ${error.message}`, 'agent');
        addEventLogItem('agent', 'Shopping Assistant', `---> Captured final response text event from Shopping Assistant: An unexpected error occurred: ${error.message} ---`);
    } finally {
        sendButton.disabled = false;
        const finalTypingIndicator = document.getElementById('typing-indicator');
        if (finalTypingIndicator) {
            finalTypingIndicator.remove();
        }
    }
}

            headingLink.addEventListener('click', (event) => {
                event.preventDefault();
                chatContainer.classList.toggle('show');
                // Removed:  eventLog.classList.toggle('show');
                if (!eventLog.classList.contains('show')) {
                    eventLog.classList.add('show');
                }

            });

            sendButton.addEventListener('click', sendMessage);

            userInput.addEventListener('keypress', function (event) {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    sendMessage();
                }
            });

            navButtons.forEach(button => {
                button.addEventListener('click', function (event) {
                    event.preventDefault();
                    const action = this.getAttribute('data-action');
                    let prompt = '';

                    switch (action) {
                        case 'search':
                            prompt = 'Search for: ';
                            break;
                        case 'status':
                            prompt = 'What is the status of order ';
                            break;
                        case 'order':
                            prompt = 'Order 1 of product ';
                            break;
                        case 'cancel':
                            prompt = 'Cancel order ';
                            break;
                        case 'list_orders':
                            prompt = 'List all my orders';
                            break;
                        default:
                            prompt = '';
                    }

                    userInput.value = prompt;
                    userInput.focus();
                    if (action === 'list_orders') {
                        sendMessage();
                    }
                });
            });

            // Initial event log entry
            addEventLogItem('system', 'System', 'Chat started.');
            eventLog.classList.add('show');


         // Make chat container draggable
        let isDragging = false;
        let offset = { x: 0, y: 0 };

        chatHeader.addEventListener('mousedown', (e) => {
        isDragging = true;
        // Calculate offset relative to the chat container's current position
        // When using 'fixed' positioning, offsetLeft/offsetTop are relative to the viewport
        offset.x = e.clientX - chatContainer.getBoundingClientRect().left;
        offset.y = e.clientY - chatContainer.getBoundingClientRect().top;

        // Set the chat container to absolute positioning to remove fixed constraints during drag
        // And reset right/bottom to allow left/top to take over
        chatContainer.style.position = 'auto'; // Keep fixed for relative to viewport
        chatContainer.style.right = 'auto'; // Disable right
        chatContainer.style.bottom = 'auto'; // Disable bottom
        chatContainer.style.left = chatContainer.getBoundingClientRect().left + 'px'; // Set current left
        chatContainer.style.top = chatContainer.getBoundingClientRect().top + 'px'; // Set current top

        chatHeader.style.cursor = 'grabbing';
        chatContainer.style.cursor = 'grabbing';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        let newX = e.clientX - offset.x;
        let newY = e.clientY - offset.y;

        const maxX = window.innerWidth - chatContainer.offsetWidth;
        const maxY = window.innerHeight - chatContainer.offsetHeight;

        newX = Math.max(0, Math.min(newX, maxX));
        newY = Math.max(0, Math.min(newY, maxY));

        chatContainer.style.left = newX + 'px';
        chatContainer.style.top = newY + 'px';
    });

    document.addEventListener('mouseup', () => {
        isDragging = false;
        chatHeader.style.cursor = 'grab';
        chatContainer.style.cursor = 'default'; // Reset cursor for the container
    });
            // ************* NEW CODE FOR CLICKING OUTSIDE *************
        document.addEventListener('click', (event) => {
        // If the chatbox is currently shown AND
        // if the click was NOT inside the chatContainer AND
        // if the click was NOT on the headingLink (which toggles it)
        if (chatContainer.classList.contains('show') &&
            !chatContainer.contains(event.target) &&
            event.target !== headingLink) {
            chatContainer.classList.remove('show');
        }
    });
        });