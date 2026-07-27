
from typing import List, Tuple, Dict
import os
from openai import OpenAI
from dotenv import load_dotenv
from backend.app.config.settings import settings

# Load environment variables
load_dotenv()

class EmbeddingService:
    """
    A service for generating text embeddings using OpenAI's API.
    """
    _instance = None
    _client = None
    _model_name = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
            
            # Initialize OpenAI client only once
            api_key = settings.openai_api_key
            base_url = None # settings.openai_base_url (If added later)
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set for EmbeddingService.")
            
            cls._client = OpenAI(api_key=api_key, base_url=base_url)
            cls._model_name = settings.rag.embedding_model
            
            # logger.debug(f"OpenAI EmbeddingService initialized with model: {cls._model_name}")
        return cls._instance

    def create_embeddings(self, texts: List[str]) -> Tuple[List[List[float]], Dict[str, int]]:
        """
        Generates embeddings for a list of texts using OpenAI's API.

        Args:
            texts: A list of strings to be embedded.

        Returns:
            A tuple containing:
            - A list of embedding vectors (each as a list of floats).
            - A dictionary with token usage details.
        """
        if not texts:
            return [], {"total_tokens": 0, "prompt_tokens": 0}
        
        BATCH_SIZE = 20  # Safe batch size to avoid total token limits per request
        all_embeddings = []
        total_usage = {"total_tokens": 0, "prompt_tokens": 0}
        
        # logger.debug(f"Generating embeddings for {len(texts)} text chunks using OpenAI model: {self._model_name}...")
        
        try:
            for i in range(0, len(texts), BATCH_SIZE):
                batch_texts = texts[i : i + BATCH_SIZE]
                
                # Ensure all inputs are strings
                safe_batch_texts = [str(t) for t in batch_texts]

                # Create embeddings
                response = self._client.embeddings.create(
                    input=safe_batch_texts,
                    model=self._model_name
                )
                
                # Append embeddings
                batch_embeddings = [data.embedding for data in response.data]
                all_embeddings.extend(batch_embeddings)
                
                # Aggregate usage
                if response.usage:
                    total_usage["total_tokens"] += response.usage.total_tokens
                    total_usage["prompt_tokens"] += response.usage.prompt_tokens
            
            # logger.debug(f"Embeddings generated successfully. Total chunks: {len(all_embeddings)}. Total usage: {total_usage}")
            return all_embeddings, total_usage
        except Exception as e:
            # logger.error(f"Error generating embeddings with OpenAI: {e}")
            raise

# Singleton instance for easy access
embedding_service = EmbeddingService()

