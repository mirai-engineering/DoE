import torch
import torch.nn as nn


class TabularMLP(nn.Module):
    def __init__(
        self,
        input_dim: int = 7,
        output_dim: int = 5,
        hidden_dims: tuple[int, ...] = (64, 64, 32),
        dropout: float = 0.0,
    ):
        super().__init__()

        layers: list[nn.Module] = []
        previous_dim = input_dim
        for hidden_dim in hidden_dims:
            layers.append(nn.Linear(previous_dim, hidden_dim))
            layers.append(nn.ReLU())
            if dropout > 0:
                layers.append(nn.Dropout(dropout))
            previous_dim = hidden_dim
        layers.append(nn.Linear(previous_dim, output_dim))

        self.network = nn.Sequential(*layers)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features)
